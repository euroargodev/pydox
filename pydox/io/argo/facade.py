"""
This module implement the logic to load and process Argo data.

These functions are expected to receive low-level setting values (no high-level object like the configuration).
"""

import logging
from copy import deepcopy
from typing import Literal, Optional

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import argopy as ar
from pathlib import Path
import shutil
import fsspec
from netCDF4 import Dataset, chartostring, stringtochar
import re
import numpy as np
from datetime import datetime

import pydox as do
from pydox._config.config import Config
from pydox.reporting.logs import getLogger
from pydox.commodities import ParameterSet, Coefficients, PlotParams, TPlotParams
from pydox.io.argo.types import MultiProfData, TrajData, CycData, ArgoDataForInAir
from pydox.io.argo.utils import (
    preprocess_raw_rtraj,
    preprocess_raw_sprof,
    cycle_select,
    get_ts_near_surface,
    code_select,
    traj_groupby_cycles,
    psal_rtraj_substitute_sprof,
    get_uid_for_in_air_method_parameters,
)


log = getLogger("pydox.io.argo.facade", context_level=0)


def get_argo_data_for_in_air_method(
    min_pres: float,
    max_pres: float,
    in_air_codes: tuple[int, ...] | list[int, ...],
    in_water_codes: tuple[int, ...] | list[int, ...],
    which_psal: int,
    cycles: tuple[int, ...] | list[int, ...],
    Sprof: xr.Dataset,
    Rtraj: xr.Dataset,
    uid: Optional[str] = None,
    ppar: Optional[TPlotParams] = None,
) -> ArgoDataForInAir | dict[str, xr.Dataset]:
    """Load Argo float data to calibrate oxygen with atmospheric data (in-air method)

    Adapted from `m_argo_data.get_argo_data_for_NCEP()`.

    Parameters
    ----------
    min_pres: float
    max_pres: float
    in_air_codes: list[int]
    in_water_codes: list[int]
    which_psal: int
    cycles: list[int]
    Sprof: xr.Dataset
    Rtraj: xr.Dataset

    Other Parameters
    ----------------
    uid: str
    ppar: TPlotParams

    Returns
    -------
    dict[str, xr.Dataset | list[int]]
        A dictionary

    Notes
    -----
    For similar set of primary parameters, new figures will be commited only if the `uid` is different.

    """
    # Get UID for this set of parameters:
    uid_suff = get_uid_for_in_air_method_parameters(
        min_pres=min_pres,
        max_pres=max_pres,
        in_air_codes=in_air_codes,
        in_water_codes=in_water_codes,
        which_psal=which_psal,
        cycles=cycles,
        Sprof=Sprof,
        Rtraj=Rtraj,
    )
    uid = f"{uid}-{uid_suff}" if uid is not None else uid_suff
    # Appending the uid_suff will allow to identify similar plots but created with higher level different configs.

    ppar: PlotParams = PlotParams.get(ppar)
    ppar.uid = (
        uid if uid is not None else ppar.uid
    )  # Ensure to use the last possible uid value

    ############################################################################################
    # Pre-process raw GDAC xr.DataSet objects
    # We sub-select only variables that we really need to work with:
    # (this makes data processing easier)
    Sprof: MultiProfData = preprocess_raw_sprof(Sprof)
    Rtraj: TrajData = preprocess_raw_rtraj(Rtraj)

    ############################################################################################
    # Select cycles to be used:
    Sprof = cycle_select(Sprof, cycle=cycles, dim="N_PROF")
    Rtraj = cycle_select(Rtraj, cycle=cycles, dim="N_MEASUREMENT")

    ############################################################################################
    # Get T,S near surface from Sprof
    sprof_near_surf = get_ts_near_surface(Sprof, min_pres, max_pres, ppar=ppar)

    ############################################################################################
    # Get In-air and In-water data

    #############
    Rtraj_inair: TrajData = code_select(Rtraj, in_air_codes)
    Rtraj_inwater: TrajData = code_select(Rtraj, in_water_codes)

    # Check NaN:
    for ds, dsname in [(Rtraj_inair, "in-air"), (Rtraj_inwater, "in-water")]:
        for pname in ["PSAL", "TEMP"]:
            if ds[pname].isnull().all():
                log.debug(
                    f"{dsname.title()} trajectory {pname} DataArray is full of NaNs !"
                )

    #############
    # Then we sub-select measurements for cycle numbers found in in-air and in-water dataset:
    shared_cycles = np.intersect1d(
        Rtraj_inair["CYCLE_NUMBER"], Rtraj_inwater["CYCLE_NUMBER"]
    ).tolist()
    Rtraj_inair: TrajData = cycle_select(Rtraj_inair, shared_cycles)
    Rtraj_inwater: TrajData = cycle_select(Rtraj_inwater, shared_cycles)

    assert np.all(
        np.unique(Rtraj_inair["CYCLE_NUMBER"])
        == np.unique(Rtraj_inwater["CYCLE_NUMBER"])
    )

    if (this_plot_level := 0) >= ppar.level:
        suptitle = "Rtraj data after code selection and cycle matching"
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=ppar.dpi, sharex=True
        )
        ax = ax.flatten()
        ylim_before_grouping = {}
        for ii, v in enumerate(v2plot):
            ax[ii].plot(
                Rtraj_inair["N_MEASUREMENT"],
                Rtraj_inair[v],
                "s-",
                linewidth=0.5,
                label="Rtraj: In-Air",
            )
            ax[ii].plot(
                Rtraj_inwater["N_MEASUREMENT"],
                Rtraj_inwater[v],
                ".-",
                linewidth=0.5,
                label="Rtraj: In-Water",
            )
            ax[ii].legend()
            ax[ii].grid(True)
            ax[ii].set_title(f"{Rtraj_inair[v].attrs['long_name']}")
            ax[ii].set_ylabel(f"{v} [{Rtraj_inair[v].attrs['units']}]")
            ylim_before_grouping[v] = ax[ii].get_ylim()
        ax[ii].set_xlabel("N_MEASUREMENT")
        plt.suptitle(suptitle)
        plt.tight_layout()
        do.figures.commit(
            fig,
            name=suptitle,
            watermark=ppar.watermark,
            category="debug",
            config_uid=ppar.uid,
        )

    #############
    # Then we reduce measurements by cycle numbers :
    # (we take the median value of all measurements from a cycle)
    Rtraj_inair: CycData = traj_groupby_cycles(Rtraj_inair)
    Rtraj_inwater: CycData = traj_groupby_cycles(Rtraj_inwater)

    # Check NaN:
    # todo Should we fall back on using TEMP from Sprof if Rtraj['TEMP'] is full of NaNs ?
    for ds, dsname in [(Rtraj_inair, "in-air"), (Rtraj_inwater, "in-water")]:
        for pname in ["PSAL", "TEMP"]:
            if ds[pname].isnull().all():
                log.debug(
                    f"{dsname.title()} trajectory {pname} DataArray is full of NaNs after group by cycles !"
                )

    if (this_plot_level := 0) >= ppar.level:
        suptitle = "In-air and In-Water Rtraj data after median-per-cycle grouping"
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=ppar.dpi, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            ax[ii].plot(
                Rtraj_inair["CYCLE_NUMBER"],
                Rtraj_inair[v],
                "s-",
                linewidth=0.5,
                label="Rtraj: In-Air",
            )
            ax[ii].plot(
                Rtraj_inwater["CYCLE_NUMBER"],
                Rtraj_inwater[v],
                ".-",
                linewidth=0.5,
                label="Rtraj: In-Water",
            )
            ax[ii].legend()
            ax[ii].grid(True)
            ax[ii].set_title(f"{Rtraj_inair[v].attrs['long_name']}")
            ax[ii].set_ylabel(f"{v} [{Rtraj_inair[v].attrs['units']}]")
            if v in ylim_before_grouping:
                ax[ii].set_ylim(ylim_before_grouping[v])

        ax[ii].set_xlabel("CYCLE_NUMBER")
        plt.suptitle(suptitle)
        plt.tight_layout()
        do.figures.commit(
            fig,
            name=suptitle,
            watermark=ppar.watermark,
            category="debug",
            config_uid=ppar.uid,
        )
    if (this_plot_level := 0) >= ppar.level:
        suptitle = "Sprof vs Rtraj In-Air and In-Water Oxygen data"

        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 5), dpi=ppar.dpi)
        ax.plot(
            Rtraj_inair["CYCLE_NUMBER"],
            Rtraj_inair["PPOX_DOXY"],
            "*-",
            linewidth=1,
            label="Rtraj: In Air",
        )
        ax.plot(
            Rtraj_inwater["CYCLE_NUMBER"],
            Rtraj_inwater["PPOX_DOXY"],
            ".-",
            linewidth=1,
            label="Rtraj: In Water",
        )

        ax.legend()
        ax.grid(True)
        ax.set_ylabel(f"PPOX_DOXY [{Rtraj_inair['PPOX_DOXY'].attrs['units']}]")
        ax.set_title(f"{Rtraj_inair['PPOX_DOXY'].attrs['long_name']}")
        ax.set_xlabel("CYCLE_NUMBER")
        plt.suptitle(suptitle)
        plt.tight_layout()

        do.figures.commit(
            fig,
            name=suptitle,
            watermark=ppar.watermark,
            category="debug",
            config_uid=ppar.uid,
        )

    if (this_plot_level := 0) >= ppar.level:
        suptitle = "Sprof vs Rtraj In-Air and In-Water T/S data"
        v2plot = ["PSAL", "TEMP"]
        ylim_before_substitution: dict = (
            {}
        )  # So that the same plot but "after substitution" can use similar y lims

        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=ppar.dpi, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            pname, plabel = None, None
            if v == "PSAL":
                pname, plabel = "psal_merged", "Sprof: merged"
            elif v == "TEMP":
                pname, plabel = "temp", "Sprof"
            if pname is not None:
                ax[ii].plot(
                    sprof_near_surf[pname]["CYCLE_NUMBER"],
                    sprof_near_surf[pname],
                    "s-",
                    linewidth=0.5,
                    label=plabel,
                )

            ax[ii].plot(
                Rtraj_inair["CYCLE_NUMBER"],
                Rtraj_inair[v],
                "*-",
                linewidth=1,
                label="Rtraj: In Air",
            )
            ax[ii].plot(
                Rtraj_inwater["CYCLE_NUMBER"],
                Rtraj_inair[v],
                ".-",
                linewidth=1,
                label="Rtraj: In Water",
            )

            ax[ii].legend()
            ax[ii].grid(True)
            ax[ii].set_ylabel(f"{v} [{Rtraj_inair[v].attrs['units']}]")
            ax[ii].set_title(f"{Rtraj_inair[v].attrs['long_name']}")
            ylim_before_substitution[v] = ax[ii].get_ylim()

        ax[ii].set_xlabel("CYCLE_NUMBER")
        plt.suptitle(suptitle)
        plt.tight_layout()
        do.figures.commit(
            fig,
            name=suptitle,
            watermark=ppar.watermark,
            category="debug",
            config_uid=ppar.uid,
        )

    #############
    # Then we replace Rtraj PSAL data with Sprof PSAL
    # todo: because ... ?
    # (Here we substitute salinity from Sprof, but it could be possible to extend this to use salinity
    # from a climatology)

    # Lookup table to match with `which_psal` configuration parameter
    lut = {
        1: sprof_near_surf["psal"],
        2: sprof_near_surf["psal_adj"],
        3: sprof_near_surf["psal_merged"],
    }

    # We create new datasets to avoid any confusion, since we now mix Sprof and Rtraj data:
    ds_inair: CycData = deepcopy(Rtraj_inair)
    ds_inwater: CycData = deepcopy(Rtraj_inwater)

    for ds in [ds_inair, ds_inwater]:
        # Execute substitution:
        ds["PSAL"] = psal_rtraj_substitute_sprof(ds["PSAL"], lut[which_psal])

        # Update dataset title to keep track of processing:
        ds.attrs["title"] = (
            f"{ds.attrs['title']} merged with some Sprof multi-profile data"
        )

    if (this_plot_level := 0) >= ppar.level:
        suptitle = (
            "Sprof vs Rtraj In-Air and In-Water T/S data - after salinity substitution"
        )
        v2plot = ["PSAL", "TEMP"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=ppar.dpi, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            pname, plabel = None, None
            if v == "PSAL":
                pname, plabel = "psal_merged", "Sprof: merged"
            elif v == "TEMP":
                pname, plabel = "temp", "Sprof"
            if pname is not None:
                ax[ii].plot(
                    sprof_near_surf[pname]["CYCLE_NUMBER"],
                    sprof_near_surf[pname],
                    "s-",
                    linewidth=0.5,
                    label=plabel,
                )

            ax[ii].plot(
                ds_inair["CYCLE_NUMBER"],
                ds_inair[v],
                "*-",
                linewidth=1,
                label="Rtraj⊕Sprof: In Air",
            )
            ax[ii].plot(
                ds_inwater["CYCLE_NUMBER"],
                ds_inwater[v],
                ".-",
                linewidth=1,
                label="Rtraj⊕Sprof: In Water",
            )

            ax[ii].legend()
            ax[ii].grid(True)
            ax[ii].set_ylabel(f"{v} [{ds_inair[v].attrs['units']}]")
            ax[ii].set_title(f"{ds_inair[v].attrs['long_name']}")
            if v in ylim_before_substitution:
                ax[ii].set_ylim(ylim_before_substitution[v])

        ax[ii].set_xlabel("CYCLE_NUMBER")
        plt.suptitle(suptitle)
        plt.tight_layout()
        do.figures.commit(
            fig,
            name=suptitle,
            watermark=ppar.watermark,
            category="debug",
            config_uid=ppar.uid,
        )

    #############
    # Then we check for diff in temperature between Rtraj and Sprof:
    for cyc in ds_inwater["CYCLE_NUMBER"]:

        t_traj = (
            ds_inwater["TEMP"]
            .loc[{"CYCLE_NUMBER": ds_inwater["CYCLE_NUMBER"] == cyc}]
            .item()
        )
        t_sprof = (
            sprof_near_surf["temp"]
            .loc[{"N_PROF": sprof_near_surf["temp"]["CYCLE_NUMBER"] == cyc}]
            .isel(N_PROF=0)
            .item()
        )
        # todo: Check if using primary profile in Sprof is always a valid choice

        if np.abs(t_traj - t_sprof) > 0.5:
            log.warning(
                f"Cycle {cyc.item()}: temperature from Rtraj in-water and Sprof differ by more than 0.5 degC ({t_traj - t_sprof:0.2f} degC) !"
            )

    #############
    # Then we affect a correct position to each cycle
    # Because for some ARGOS float (with Iridium Position, not GPS), the position are recalculated.
    # So, it's better to take the position from the Sprof file, where the position are OK.

    for cyc in ds_inair["CYCLE_NUMBER"]:

        this = Sprof.loc[{"N_PROF": Sprof["CYCLE_NUMBER"] == cyc}]

        if len(this["N_PROF"]) == 0:
            log.debug(f"Cycle number {cyc.values} is in Rtraj but not in Sprof !")
            lat, lon, pqc = np.nan, np.nan, 0
        else:
            # Use data from primary profile:
            # todo: Check if using primary profile in Sprof is always a valid choice
            lat, lon, pqc = (
                this["LATITUDE"].isel(N_PROF=0).item(),
                this["LONGITUDE"].isel(N_PROF=0).item(),
                this["POSITION_QC"].isel(N_PROF=0).item(),
            )

        for ds in [ds_inair, ds_inwater]:
            for pname, pvalue in [
                ("LATITUDE", lat),
                ("LONGITUDE", lon),
                ("POSITION_QC", pqc),
            ]:
                ds[pname].loc[{"CYCLE_NUMBER": ds["CYCLE_NUMBER"] == cyc}] = pvalue

    ############################################################################################

    # We return data organized with a dataclass:
    return ArgoDataForInAir(
        in_air=ds_inair,
        in_water=ds_inwater,
        Sprof=Sprof,
        Rtraj=Rtraj,
        optode_height=None,
        launch_date=None,
    )


def semantic_cycle2values(
    a_float: ar.ArgoFloat,
    settings: Config | ParameterSet,
    group: Literal["calibration_parameters", "adjustment"] = "calibration_parameters",
    dsname: Literal["Sprof"] = "Sprof",
) -> tuple[int, ...]:
    """Convert a cycle range to a list of cycle numbers, handle semantic like 'first' and 'last'

    Parameters
    ----------
    a_float: ar.ArgoFloat
        The :class:`ar.ArgoFloat` object to read cycle numbers from.
    settings: Config | ParameterSet
        Object to read a `cycles` setting from.
    group: str, default='calibration_parameters'
        Name of the configuration group to read cycles from. Can be "calibration_parameters" or "adjustment".
    dsname: str, default='Sprof'
        Name of the :class:`ar.ArgoFloat` dataset to read cycle numbers from.

    Returns
    -------
    tuple[int]
    """
    ds: xr.Dataset = a_float.dataset(dsname)
    if "CYCLE_NUMBER" not in ds.data_vars:
        raise ValueError(
            f"'CYCLE_NUMBER' is a mandatory dataset variable for this function, and it cannot be found in '{dsname}'."
        )

    try:
        semantic_cycles: tuple = do.get_params(f"{group}.cycles", config=settings)
    except Exception as e:
        if isinstance(settings, ParameterSet):
            semantic_cycles: tuple = settings.cycles
        else:
            raise e

    if semantic_cycles[0] == "first":
        cycle_first = ds["CYCLE_NUMBER"].min().item()
    elif semantic_cycles[0] in ds["CYCLE_NUMBER"]:
        cycle_first = semantic_cycles[0]
    else:
        raise NotImplementedError(
            f"Unsupported value for calibration_parameters.cycles[0]: '{semantic_cycles[0]}'"
        )

    if semantic_cycles[-1] == "last":
        cycle_last = ds["CYCLE_NUMBER"].max().item()
    elif semantic_cycles[-1] in ds["CYCLE_NUMBER"]:
        cycle_last = semantic_cycles[-1]
    else:
        raise NotImplementedError(
            f"Unsupported value for calibration_parameters.cycles[-1]: '{semantic_cycles[-1]}'"
        )

    if cycle_last <= cycle_first:
        raise ValueError(
            f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles}). It must be ordered and increasing"
        )

    values = ds["CYCLE_NUMBER"].values
    cycles = values[np.logical_and(values >= cycle_first, values <= cycle_last)]
    return tuple([int(c) for c in cycles])


def string_var(data_src, name, txt, strlen=None):
    """
    Function to generate variable with string dimensions.

    Parameters
    ----------
    data_src: Dataset
    name : str : Vraiable name
    txt : str : Text associated to this variable
    strlen : type of the variable (length of the strin)

    return a string with the good type (S1, S14, ...)
    """
    if strlen is None:
        idx = next(i for i, d in enumerate(data_src[name].dimensions) if "STRING" in d)
        strlen = data_src[name].shape[idx]

    str_array = np.array([txt.ljust(strlen)], dtype=f"S{strlen}")

    if len(data_src[name].shape) == 1:
        return stringtochar(str_array)
    else:
        return stringtochar(str_array)[0]


def corr_B_files(data_float: ar.ArgoFloat, coef_kept: Coefficients):
    """Function to read B files associated to the ArgoFloat, correct the DOXY_ADJUSTED using coef_kept, update the associated QC, SCIENTIFIC_CALIB*, ...
    and generate the corrected B files (BD files).
    DOXY_ADJUSTED = (coef_kept.gain * (1 + coef_kept.drift/100* (juld_day - juld_day_launch)/365) * DOXY.
    In the future, we will apply a pressure correction determined by comparison DOXY CTD with ARGO DOXY.
    This pressure correction will estimate on DOXY, that's why we decided to correct the DOXY and not the PPOX.

    Parameters
    ----------
    data_float: ar.ArgoFloat
        The :class:`ar.ArgoFloat` object to read cycle numbers from.
    coef_kept : Coefficients
        contains the final gain/drift to apply to correct the DOXY data

    Returns
    -------
        None
        The function generates BD files with corrected DOXY in DOXY_ADJUSTED. Variables depending of N_CALIB and N_HISTORY are updated, as the update_date.

    """

    cycles_to_write = semantic_cycle2values(
        data_float, settings=None, group="adjustment"
    )
    print(cycles_to_write)

    dims_to_extend = {"N_CALIB", "N_HISTORY"}  # We add a new calibration

    # List of B files to be modified
    list_files = data_float.lsprofiles()
    list_Bfiles = [
        f for f in list_files if Path(f).name.startswith("B")
    ]  # list of B files (ascending/descending in realtime or delayed mode)

    # Output directory/ relative error
    rep_res = (
        Path(do.get_params("output.root"))
        .joinpath(f"{data_float.WMO}")
        .joinpath(do.get_params("adjustment.save.path"))
    )
    if not Path(rep_res).exists():
        Path(rep_res).mkdir(parents=True, exist_ok=True)

    relative_error = do.get_params("adjustment.relative_error")

    print("Correction used :")
    print(f"gain : {coef_kept.gain}")

    if coef_kept.drift is None:
        print("No drift applied")
    else:
        print(f"drift : {coef_kept.drift}")

    # For each B file
    for i_fic in range(0, len(list_Bfiles)):
        file_in_progress = list_Bfiles[i_fic]
        bid = re.match(
            r".*_(\d+)[A-Z]?\.nc$", file_in_progress
        )  # We look for the number after the underscore, ie the cycle number
        cycle_en_cours = int(
            bid.group(1)
        )  # group(1) : 1st group  (the number in the parenthesis : (\d+))
        if min(cycles_to_write) <= cycle_en_cours <= max(cycles_to_write):
            file_src = Path(rep_res).joinpath(
                Path(file_in_progress).name.replace(".nc", "_new.nc")
            )  # os.path.join(rep_res,os.path.basename(file_in_progress.replace(".nc","_new.nc")))
            file_adj = Path(rep_res).joinpath(
                Path(file_in_progress).name.replace(".nc", "_new2.nc")
            )  # os.path.join(rep_res,os.path.basename(file_in_progress.replace(".nc","_new2.nc")))

            # We copy the input file (which can be on local disk but also on internet) in the output directory.
            with (
                fsspec.open(file_in_progress, "rb") as src,
                open(file_src, "wb") as dst,
            ):
                shutil.copyfileobj(src, dst)

            # We generate the output file from 'scratch'.
            data_src = Dataset(file_src, "r+")  # Data from Input file
            data_adj = Dataset(
                file_adj, "w"
            )  # Data to be registered in the Output/adjusted file
            data_src.set_auto_mask(
                False
            )  # File BD6902882_075.nc. C1PHASE_DOXY=0.71 with C1PHASE_DOXY_QC=1 but C1PHASE_DOXY.valid_min = 10.
            # Without this instruction, 0.71 is replaced by FillValue. So, in the output file, 0.71 is also replaced by FillValue

            # DOXY Indice in PARAMETER
            params = np.char.strip(chartostring(data_src["PARAMETER"][:]))
            i_param = np.where(params[0, 0] == "DOXY")[0][0]

            # Number of profile and calibration
            nb_prof = data_src.dimensions["N_PROF"].size
            nb_calib = data_src.dimensions["N_CALIB"].size
            nb_calib_new = nb_calib + 1  # We add 1 calibration in the adjusted file
            nb_history = data_src.dimensions["N_HISTORY"].size
            nb_history_new = nb_history + 1  # We add 1 history in the adjusted file

            # Copy global attributs from input data to adjusted data
            global_attr = data_src.ncattrs()
            for name_attr in global_attr:
                value_attr = data_src.getncattr(name_attr)
                data_adj.setncattr(name_attr, value_attr)

            # Copy dimensions from input data to adjusted data
            for name, dim in data_src.dimensions.items():
                if name == "N_CALIB":  # in dims_to_extend: N_HISTORY must be UNLIMITED
                    data_adj.createDimension(name, len(dim) + 1)  # add 1 for N_CALIB
                else:
                    data_adj.createDimension(
                        name, len(dim) if not dim.isunlimited() else None
                    )

            # Date
            date_str = datetime.now().strftime("%Y%m%d%H%M%S")
            date_strlen = len(date_str)
            # Copy variables from input data to adjusted data
            for name, var in data_src.variables.items():
                out_var = data_adj.createVariable(
                    name,
                    var.dtype,
                    var.dimensions,
                    fill_value=getattr(var, "_FillValue", None),
                )

                # Copy variable attributs
                var_attrs = var.ncattrs()
                for k in var_attrs:
                    if k != "_FillValue":
                        value_attr = var.getncattr(k)
                        out_var.setncattr(k, value_attr)
                data = var[:]

                # Does the current variable depends on N_CALIB or N_HISTORY ?
                extend_axes = [
                    i for i, d in enumerate(var.dimensions) if d in dims_to_extend
                ]

                if extend_axes:  # If YES

                    new_shape = list(data.shape)

                    for axis in extend_axes:
                        new_shape[axis] += 1  # We add a new calibration

                    fill_value = getattr(var, "_FillValue", None)
                    # Creation of new_data
                    if fill_value is not None:
                        new_data = np.full(new_shape, fill_value, dtype=data.dtype)
                    else:
                        new_data = np.zeros(new_shape, dtype=data.dtype)

                    # Old data at the beggining
                    slices = [slice(0, s) for s in data.shape]
                    new_data[tuple(slices)] = (
                        data  # We copy the existing data in the previous calibration or history. The sub-array of new_data that is common with data is initialized to data.
                    )

                    # For each profiles N_PROF : We complete the new calibration information.
                    for i_prof in range(0, nb_prof):
                        if "SCIENTIFIC_CALIB" in name or name == "PARAMETER":
                            new_data[i_prof, nb_calib_new - 1, :, :] = new_data[
                                i_prof, nb_calib_new - 2, :, :
                            ]  # Copy the information from the previous calibration in the new one
                        elif (
                            name == "HISTORY_START_PRES"
                            or name == "HISTORY_STOP_PRES"
                            or name == "HISTORY_PREVIOUS_VALUE"
                        ):
                            new_data[nb_history_new - 1, i_prof] = new_data[
                                nb_history_new - 2, i_prof
                            ]  # Copy the information from the previous history in the new one
                        else:
                            new_data[nb_history_new - 1, i_prof, :] = new_data[
                                nb_history_new - 2, i_prof, :
                            ]  # Copy the information from the previous history in the new one

                        # Update DATA_MODE and PARAMETR_DATA_MODE for DOXY
                        if name == "DATA_MODE":
                            data_adj["DATA_MODE"][i_prof] = b"D"

                        if name == "PARAMETER_DATA_MODE":
                            data_adj["PARAMETER_DATA_MODE"][i_prof, i_param] = b"D"

                        # Update SCIENTIFIC_CALIB_ variables
                        if name == "SCIENTIFIC_CALIB_COMMENT":
                            new_data[i_prof, nb_calib_new - 1, i_param, :] = string_var(
                                data_src, name, "Data Corrected with Pydox"
                            )

                        if name == "SCIENTIFIC_CALIB_EQUATION":
                            new_data[i_prof, nb_calib_new - 1, i_param, :] = string_var(
                                data_src,
                                name,
                                "Data Corrected with following equation : DOXY_Adjusted = DOXY * gain * (1+drift/100*Delta_T/365))",
                            )

                        if name == "SCIENTIFIC_CALIB_COEFFICIENT":
                            if coef_kept.drift is None:
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = (
                                    string_var(
                                        data_src,
                                        name,
                                        f"Gain : {coef_kept.gain.value}, No drift applied",
                                    )
                                )
                            else:
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = (
                                    string_var(
                                        data_src,
                                        name,
                                        f"Gain : {coef_kept.gain.value}, drift : {coef_kept.drift.value}",
                                    )
                                )

                        if name == "SCIENTIFIC_CALIB_DATE":
                            new_data[i_prof, nb_calib_new - 1, i_param, :] = string_var(
                                data_src, name, date_str, date_strlen
                            )

                        if name == "HISTORY_INSTITUTION":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "IF"
                            )

                        if name == "HISTORY_ACTION":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "CV"
                            )

                        if name == "HISTORY_SOFTWARE":
                            # todo : Define the software name and version in the config ?
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "PYDO"
                            )

                        if name == "HISTORY_SOFTWARE_RELEASE":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "V0"
                            )

                        if name == "HISTORY_STEP":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "ARSQ"
                            )
                        if name == "HISTORY_REFERENCE":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, " "
                            )

                        if name == "HISTORY_PARAMETER":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, "DOXY"
                            )

                        if name == "HISTORY_START_PRES":
                            new_data[nb_history_new - 1, i_prof] = np.min(
                                data_src["PRES"][i_prof, :]
                            )

                        if name == "HISTORY_STOP_PRES":
                            pres = data_src["PRES"][i_prof, :]
                            fill = data_src["PRES"]._FillValue
                            valid_pres = pres[pres != fill]
                            if valid_pres.size > 0:
                                max_pres = np.max(pres[pres != fill])
                            else:
                                max_pres = fill
                            new_data[nb_history_new - 1, i_prof] = max_pres

                        if name == "HISTORY_DATE":
                            new_data[nb_history_new - 1, i_prof, :] = string_var(
                                data_src, name, date_str, date_strlen
                            )

                    out_var[:] = new_data

                else:  # N_CALIB and N_HISTORY not in the variable's dimension : we copy the input data
                    out_var[:] = data

            # We correct the DOXY_ADJUSTED by applying the equation : DOXY_ADJUSTED = DOXY * gain * (1 + drift/100 * delta_T/365). We apply the correction directly to the DOXY, not on PPOX.
            # As PPOX = value(S,T) * DOXY, the results are the same.
            # todo : must be checked with VT
            juld_var = data_adj["JULD"]
            ref_date = re.search(r"days since (.+?) UTC", juld_var.units).group(1)
            ref_date = np.datetime64(ref_date)
            date_juld = ref_date + (data_adj["JULD"][:].data * 86400).astype(
                "timedelta64[s]"
            )
            delta_T_Ref = (
                date_juld - data_float.dataset("meta")["LAUNCH_DATE"].values
            ) / np.timedelta64(1, "D")

            # DOXY_ADJUSTED_QC
            # todo : must be checked with VT
            data_adj["DOXY_ADJUSTED_QC"][:] = data_adj["DOXY_QC"][:]
            mask = np.isin(
                data_adj["DOXY_QC"][:].data, [b"1", b"2", b"3"]
            )  # & ds_ctd['PSAL_QC'].isin([1,2,3]) & ds_ctd['PRES_QC'].isin([1,2,3])) # Flag DOXY_QC in1/2/3 AND PSAL_QC/PRES_QC>=3 ==> flag 1 because they are corrected
            data_adj["DOXY_ADJUSTED_QC"][:] = np.where(
                mask, b"1", data_adj["DOXY_ADJUSTED_QC"][:]
            )

            # Apply the correction
            data_adj["DOXY_ADJUSTED"][:] = data_adj["DOXY"][:] * coef_kept.gain.value
            if coef_kept.drift is not None:
                data_adj["DOXY_ADJUSTED"][:] = data_adj["DOXY_ADJUSTED"][:] * (
                    1 + coef_kept.drift.value / 100 * delta_T_Ref[:, np.newaxis] / 365
                )

            # DOXY_ADJUSTED must be FillValue when DOXY is fillvalue and when QC is 4 or 9..
            data_adj["DOXY_ADJUSTED"][:] = np.where(
                data_adj["DOXY"][:].mask,
                data_adj["DOXY"]._FillValue,
                data_adj["DOXY_ADJUSTED"][:],
            )
            mask = np.isin(data_adj["DOXY_ADJUSTED_QC"][:].data, [b"4", b"9"])
            data_adj["DOXY_ADJUSTED"][:] = np.where(
                mask, data_adj["DOXY_ADJUSTED"]._FillValue, data_adj["DOXY_ADJUSTED"][:]
            )

            # DOXY_ADJUSTED_ERROR
            data_adj["DOXY_ADJUSTED_ERROR"][:] = (
                data_adj["DOXY_ADJUSTED"][:] * relative_error / 100
            )
            data_adj["DOXY_ADJUSTED_ERROR"][:] = np.where(
                data_adj["DOXY_ADJUSTED"][:].mask,
                data_adj["DOXY_ADJUSTED_ERROR"]._FillValue,
                data_adj["DOXY_ADJUSTED_ERROR"][:],
            )

            # Global profile QC
            good_flags = [b"1", b"2", b"5", b"8"]
            bad_flags = [b"3", b"4"]
            for i_prof in range(0, nb_prof):
                doxy_qc_en_cours = data_adj["DOXY_ADJUSTED_QC"][i_prof]
                good_count = np.isin(doxy_qc_en_cours, good_flags).sum()
                bad_count = np.isin(doxy_qc_en_cours, bad_flags).sum()
                total = good_count + bad_count  # flag 0 and 9 are ignored
                if total != 0:
                    if good_count == total:  # All DOXY_QC are good
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b"A"
                    elif good_count / total >= 0.75:  # 75%  DOXY_QC are good
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b"B"
                    elif good_count / total >= 0.5:  # 50%  DOXY_QC are good
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b"C"
                    elif good_count / total >= 0.25:  # 25%  DOXY_QC are good
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b"D"
                    elif good_count / total > 0:  # less than 25%  DOXY_QC are good
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b"E"
                    else:
                        data_adj["PROFILE_DOXY_QC"][i_prof] = b" "  # b'F' ?

            data_adj["DATE_UPDATE"][:] = string_var(
                data_src, "DATE_UPDATE", date_str, date_strlen
            )
            data_adj.close()  # This generates the final file
            data_src.close()
            # Remove the input file and rename the output file with argo convetion.
            Path(file_src).unlink()
            dirname = Path(file_adj).parent
            basename = Path(file_adj).name
            newname = Path(dirname).joinpath(
                ("BD" + basename[2:].replace("_new2.nc", ".nc"))
            )
            Path(file_adj).rename(newname)
            print(f"File {newname} created")
