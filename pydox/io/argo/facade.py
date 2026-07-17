"""
This module implement the logic to load and process Argo data.

These functions are expected to receive low-level setting values (no high-level object like the configuration).
"""

import logging
from copy import deepcopy
from typing import Literal

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import argopy as ar
from pathlib import Path
import shutil
import fsspec
from netCDF4 import Dataset
from netCDF4 import chartostring
from netCDF4 import stringtochar
import re
import numpy as np
from datetime import datetime

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParameterSet, Coefficients
from pydox.io.argo.types import MultiProfData, TrajData, CycData, ArgoDataForInAir
from pydox.io.argo.utils import (
    preprocess_raw_rtraj,
    preprocess_raw_sprof,
    cycle_select,
    get_ts_near_surface,
    code_select,
    traj_groupby_cycles,
    psal_rtraj_substitute_sprof,
)

log = logging.getLogger("pydox.io.argo.facade")


def get_argo_data_for_in_air_method(
    min_pres: float,
    max_pres: float,
    in_air_codes: tuple[int, ...],
    in_water_codes: tuple[int, ...],
    which_psal: int,
    cycles: tuple[int, ...],
    Sprof: xr.Dataset,
    Rtraj: xr.Dataset,
    debug_plot: bool = False,
) -> ArgoDataForInAir | dict[str, xr.Dataset]:
    """Load Argo float data to calibrate oxygen with atmospheric data (in-air method)

    Adapted from `m_argo_data.get_argo_data_for_NCEP()`

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
    debug_plot: bool = False

    Returns
    -------
    dict[str, xr.Dataset | list[int]]
        A dictionary
    """
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
    sprof_near_surf = get_ts_near_surface(
        Sprof, min_pres, max_pres, debug_plot=debug_plot
    )

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

    if debug_plot:
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            Rtraj_inair[v].plot.line("s-", linewidth=0.5, label="In Air", ax=ax[ii])
            Rtraj_inwater[v].plot.line(".-", linewidth=0.5, label="In Water", ax=ax[ii])
            ax[ii].legend()
            ax[ii].grid()
            ax[ii].set_title(f"{v}")
        plt.suptitle(f"Rtraj data after code selection and cycle matching")
        plt.tight_layout()
        plt.show()

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

    if debug_plot:
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            Rtraj_inair[v].plot.line("s-", linewidth=0.5, label="In Air", ax=ax[ii])
            Rtraj_inwater[v].plot.line(".-", linewidth=0.5, label="In Water", ax=ax[ii])
            ax[ii].legend()
            ax[ii].grid()
            ax[ii].set_title(f"{v}")
        plt.suptitle(f"In-air and in-water Rtraj data after median-per-cycle grouping")
        plt.tight_layout()
        plt.show()

    if debug_plot:
        # Super-impose Sprof data:
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            if v == "PSAL":
                # ax[ii].plot(spsal['CYCLE_NUMBER'], spsal.values, 's-', linewidth=0.5, label='Sprof')
                # ax[ii].plot(spsal_adj['CYCLE_NUMBER'], spsal.values, 's-', linewidth=0.5, label='Sprof: adj')
                ax[ii].plot(
                    sprof_near_surf["psal_merged"]["CYCLE_NUMBER"],
                    sprof_near_surf["psal_merged"].values,
                    "s-",
                    linewidth=0.5,
                    label="Sprof: merged",
                )
            if v == "TEMP":
                ax[ii].plot(
                    sprof_near_surf["temp"]["CYCLE_NUMBER"],
                    sprof_near_surf["temp"].values,
                    "s-",
                    linewidth=0.5,
                    label="Sprof",
                )
            Rtraj_inair[v].plot.line(
                "*-", linewidth=1, label="Rtraj: In Air", ax=ax[ii]
            )
            Rtraj_inwater[v].plot.line(
                ".-", linewidth=1, label="Rtraj: In Water", ax=ax[ii]
            )
            ax[ii].legend()
            ax[ii].grid()
            ax[ii].set_title(f"{v}")
        plt.suptitle(f"Sprof vs in-air and in-water Rtraj data")
        plt.tight_layout()
        plt.show()

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

    if debug_plot:
        v2plot = ["PSAL", "TEMP"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            if v == "PSAL":
                # ax[ii].plot(spsal['CYCLE_NUMBER'], spsal.values, 's-', linewidth=0.5, label='Sprof')
                # ax[ii].plot(spsal_adj['CYCLE_NUMBER'], spsal.values, 's-', linewidth=0.5, label='Sprof: adj')
                ax[ii].plot(
                    sprof_near_surf["psal_merged"]["CYCLE_NUMBER"],
                    sprof_near_surf["psal_merged"].values,
                    "s-",
                    linewidth=0.5,
                    label="Sprof: merged",
                )
            if v == "TEMP":
                ax[ii].plot(
                    sprof_near_surf["temp"]["CYCLE_NUMBER"],
                    sprof_near_surf["temp"].values,
                    "s-",
                    linewidth=0.5,
                    label="Sprof",
                )
            ds_inair[v].plot.line("*-", linewidth=1, label="In Air", ax=ax[ii])
            ds_inwater[v].plot.line(".-", linewidth=1, label="In Water", ax=ax[ii])
            ax[ii].legend()
            ax[ii].grid()
            ax[ii].set_title(f"{v}")
        plt.suptitle(f"Sprof vs in-air and in-water Rtraj data after substitution")
        plt.tight_layout()
        plt.show()

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
    dsname: Literal["Sprof"] = "Sprof",
) -> list[int]:
    """Convert a cycle range to a list of cycle numbers, handle semantic like 'first' and 'last'

    Parameters
    ----------
    a_float: ar.ArgoFloat
        The :class:`ar.ArgoFloat` object to read cycle numbers from.
    settings: Config | ParameterSet
        Object to read a `cycles` setting from.
    dsname: str, default='Sprof'
        Name of the :class:`ar.ArgoFloat` dataset to read cycle numbers from.

    Returns
    -------
    list[int]
    """
    ds: xr.Dataset = a_float.dataset(dsname)
    if "CYCLE_NUMBER" not in ds.data_vars:
        raise ValueError(
            f"'CYCLE_NUMBER' is a mandatory dataset variable for this function, and it cannot be found in '{dsname}'."
        )

    try:
        semantic_cycles: tuple = do.get_params(
            "calibration_parameters.cycles", config=settings
        )
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
            f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles})!"
        )

    values = ds["CYCLE_NUMBER"].values
    cycles = values[np.logical_and(values >= cycle_first, values <= cycle_last)]
    return [int(c) for c in cycles]


def corr_B_files(data_float: ar.ArgoFloat, coef_kept: Coefficients):
    """ Function to read B files associated to the ArgoFloat, correct the DOXY_ADJUSTED, update the associated QC, SCIENTIFIC_CALIB*, ...
        and generate the corrected B files (BD files).
    """

    semantic_cycles = do.get_params("adjustment.cycles")
    if semantic_cycles[0] == "first":
        cycle_first = data_float.dataset('Sprof')['CYCLE_NUMBER'].min().item()
    else:
        cycle_first = semantic_cycles[0]
    if semantic_cycles[-1] == "last":
        cycle_last = data_float.dataset('Sprof')['CYCLE_NUMBER'].max().item()
    else:
        cycle_last = semantic_cycles[-1]

    cycles_to_write = [cycle_first, cycle_last]
    print(cycles_to_write)

    dims_to_extend = {"N_CALIB", "N_HISTORY"}  # We add a new calibration

    good_flags = [b'1', b'2', b'5', b'8']
    bad_flags = [b'3', b'4']

    # List of B files to be modified
    list_files = data_float.lsprofiles()
    list_Bfiles = [f for f in list_files if
                   Path(f).name.startswith("B")]  # list of B files (ascending/descending in realtime or delayed mode)

    # Output directory/ relative error
    rep_res = Path(do.get_params('output.root')) / str(data_float.WMO) / do.get_params("adjustment.save.path")
    if not Path(rep_res).exists():
        Path(rep_res).mkdir(parents=True, exist_ok=True)

    relative_error = do.get_params("adjustment.relative_error")

    # For each B file
    for i_fic in range(0, len(list_Bfiles)):
        fic_en_cours = list_Bfiles[i_fic]
        bid = re.match(r".*_(\d+)[A-Z]?\.nc$",
                       fic_en_cours)  # On recherche les chiffres apres '_', ie le numero de cycle.
        cycle_en_cours = int(bid.group(1))  # group(1) : 1er groupe capture (ie entre parenthese : (\d+))
        if min(cycles_to_write) <= cycle_en_cours <= max(cycles_to_write):
            res_file = Path(rep_res) / Path(fic_en_cours).name.replace(".nc",
                                                                       "_new.nc")  # os.path.join(rep_res,os.path.basename(fic_en_cours.replace(".nc","_new.nc")))
            res_file2 = Path(rep_res) / Path(fic_en_cours).name.replace(".nc",
                                                                        "_new2.nc")  # os.path.join(rep_res,os.path.basename(fic_en_cours.replace(".nc","_new2.nc")))

            # We copy the input file (which can be on local disk but also on internet) in the output directory.
            # We copy this input file in the output file.
            with fsspec.open(fic_en_cours, "rb") as src, open(res_file, "wb") as dst:
                shutil.copyfileobj(src, dst)
                data_file = Dataset(res_file, 'r+')  # Data from Input file
                data_file2 = Dataset(res_file2, 'w')  # Data to be register in the Output file
                data_file.set_auto_mask(
                    False)  # Fichier BD6902882_075.nc. C1PHASE_DOXY=0.71 with C1PHASE_DOXY_QC=1 but C1PHASE_DOXY.valid_min = 10.
                # Without this instruction, 0.71 is replaced by FillValue. So, in the output file, 0.71 is also replaced by FillValue

                # DOXY Indice in PARAMETER
                params = np.char.strip(chartostring(data_file["PARAMETER"][:]))
                i_param = np.where(params[0, 0] == "DOXY")[0][0]

                # Number of profile and calibration
                nb_prof = data_file.dimensions['N_PROF'].size
                nb_calib = data_file.dimensions['N_CALIB'].size
                nb_calib_new = nb_calib + 1  # We add 1 calibration
                nb_history = data_file.dimensions['N_HISTORY'].size
                nb_history_new = nb_history + 1

                data_file2.setncatts(data_file.__dict__)  # Copy all global attributs from input data in output data

                # We copy the dimension
                for name, dim in data_file.dimensions.items():
                    if name in dims_to_extend:
                        data_file2.createDimension(name, len(dim) + 1)  # add 1 for N_CALIB
                    else:
                        data_file2.createDimension(name, len(dim) if not dim.isunlimited() else None)

                # We copy the variables
                for name, var in data_file.variables.items():
                    # Force a fillvalue
                    fill_value = getattr(var, "_FillValue", None)
                    if fill_value is not None:
                        out_var = data_file2.createVariable(
                            name,
                            var.dtype,
                            var.dimensions,
                            fill_value=fill_value
                        )
                    else:
                        out_var = data_file2.createVariable(
                            name,
                            var.dtype,
                            var.dimensions
                        )

                    # We copy the variable's attribut
                    attrs = {
                        k: v for k, v in var.__dict__.items()
                        if k != "_FillValue"
                    }
                    out_var.setncatts(attrs)

                    data = var[:]

                    # Does the current variable depends on N_CALIB or N_HISTORY ?
                    extend_axes = [
                        i for i, d in enumerate(var.dimensions)
                        if d in dims_to_extend
                    ]

                    if extend_axes:  # If YES

                        new_shape = list(data.shape)

                        for axis in extend_axes:
                            new_shape[axis] += 1  # We add a new calibration

                        # Creation of new_data
                        if fill_value is not None:
                            new_data = np.full(
                                new_shape,
                                fill_value,
                                dtype=data.dtype
                            )
                        else:
                            new_data = np.zeros(
                                new_shape,
                                dtype=data.dtype
                            )

                        if name == "PARAMETER":
                            data = np.concatenate([data, data], axis=axis)

                        # axis_calib = data_file[name].dimensions.index("N_CALIB")
                        # axis_nprof = data_file[name].dimensions.index("N_PROF")

                        # Old data at the beggining
                        slices = [slice(0, s) for s in data.shape]
                        new_data[tuple(
                            slices)] = data  # We copy the existing data in the previous calibration. The sub-array of new_data that is mommon with data is initialized to data.

                        # For each profiles N_PROF : We complete the new calibration information.
                        for i_prof in range(0, nb_prof):

                            # Update DATA_MODE and PARAMETR_DATA_MODE for DOXY
                            data_file2["DATA_MODE"][i_prof] = b'D'
                            data_file2["PARAMETER_DATA_MODE"][i_prof, i_param] = b'D'

                            # Update SCIENTIFIC_CALIB_ variables
                            if name == 'SCIENTIFIC_CALIB_COMMENT':
                                idx = next(i for i, d in enumerate(data_file['SCIENTIFIC_CALIB_COMMENT'].dimensions) if
                                           "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = \
                                stringtochar(np.array(["Data Corrected with Pydox "], dtype=f"S{strlen}"))[0]

                            if name == 'SCIENTIFIC_CALIB_EQUATION':
                                idx = next(i for i, d in enumerate(data_file['SCIENTIFIC_CALIB_EQUATION'].dimensions) if
                                           "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = stringtochar(np.array([
                                                                                                           "Data Corrected with following equation : DOXY_Adjusted = DOXY * gain * (1+drift/100*Delta_T/365))"],
                                                                                                       dtype=f"S{strlen}"))[
                                    0]

                            if name == 'SCIENTIFIC_CALIB_COEFFICIENT':
                                idx = next(
                                    i for i, d in enumerate(data_file['SCIENTIFIC_CALIB_COEFFICIENT'].dimensions) if
                                    "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = stringtochar(
                                    np.array([f"Gain : {coef_kept.gain.value}, drift : {coef_kept.drift.value}"],
                                             dtype=f"S{strlen}"))[0]  # 'merdum'

                            if name == 'SCIENTIFIC_CALIB_DATE':
                                date_str = datetime.now().strftime("%Y%m%d%H%M%S")
                                strlen = len(date_str)
                                new_data[i_prof, nb_calib_new - 1, i_param, :] = \
                                stringtochar(np.array([date_str], dtype=f"S{strlen}"))[0]
                                data_file2["DATE_UPDATE"][:] = stringtochar(np.array([date_str], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_INSTITUTION':
                                idx = next(i for i, d in enumerate(data_file['HISTORY_INSTITUTION'].dimensions) if
                                           "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["IF".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_ACTION':
                                idx = next(
                                    i for i, d in enumerate(data_file['HISTORY_ACTION'].dimensions) if "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["CV".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_SOFTWARE':
                                idx = next(
                                    i for i, d in enumerate(data_file['HISTORY_SOFTWARE'].dimensions) if "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["PYDO"], dtype=f"S{strlen}"))[
                                    0]  # todo : Define the software name and version in the config ?

                            if name == 'HISTORY_SOFTWARE_RELEASE':
                                idx = next(i for i, d in enumerate(data_file['HISTORY_SOFTWARE_RELEASE'].dimensions) if
                                           "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["V0".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_STEP':
                                idx = next(
                                    i for i, d in enumerate(data_file['HISTORY_STEP'].dimensions) if "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["ARQS".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_REFERENCE':
                                idx = next(
                                    i for i, d in enumerate(data_file['HISTORY_REFERENCE'].dimensions) if "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array([" ".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_PARAMETER':
                                idx = next(
                                    i for i, d in enumerate(data_file['HISTORY_PARAMETER'].dimensions) if "STRING" in d)
                                strlen = data_file[name].shape[idx]
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array(["DOXY".ljust(strlen)], dtype=f"S{strlen}"))[0]

                            if name == 'HISTORY_START_PRES':
                                new_data[nb_history_new - 1, i_prof] = np.min(data_file['PRES'][i_prof, :])

                            if name == 'HISTORY_STOP_PRES':
                                pres = data_file['PRES'][i_prof, :]
                                fill = data_file['PRES']._FillValue
                                valid_pres = pres[pres != fill]
                                if valid_pres.size > 0:
                                    max_pres = np.max(pres[pres != fill])
                                else:
                                    max_pres = fill
                                new_data[nb_history_new - 1, i_prof] = max_pres

                            if name == 'HISTORY_DATE':
                                date_str = datetime.now().strftime("%Y%m%d%H%M%S")
                                strlen = len(date_str)
                                new_data[nb_history_new - 1, i_prof, :] = \
                                stringtochar(np.array([date_str], dtype=f"S{strlen}"))[0]

                        out_var[:] = new_data

                    else:  # N_CALIB not in the variable's dimension : we copy the input data
                        out_var[:] = data

            # We correct the DOXY_ADJUSTED by applying the equation : DOXY_ADJUSTED = DOXY * gain * (1 + drift/100 * delta_T/365). We apply the correction directly to the DOXY, not on PPOX.
            # As PPOX = value(S,T) * DOXY, the results are the same.
            # todo : must be checked with VT
            juld_var = data_file2["JULD"]
            ref_date = re.search(r"since (.+?) UTC", juld_var.units).group(1)
            ref_date = np.datetime64(ref_date)
            date_juld = ref_date + (data_file2["JULD"][:].data * 86400).astype('timedelta64[s]')
            delta_T_Ref = (date_juld - data_float.dataset("meta")["LAUNCH_DATE"].values) / np.timedelta64(1, "D")

            # DOXY_ADJUSTED_QC
            # todo : must be checked with VT
            data_file2['DOXY_ADJUSTED_QC'][:] = data_file['DOXY_QC'][:]
            mask = np.isin(data_file2['DOXY_QC'][:].data, [b'1', b'2',
                                                           b'3'])  # & ds_ctd['PSAL_QC'].isin([1,2,3]) & ds_ctd['PRES_QC'].isin([1,2,3])) # Flag DOXY_QC in1/2/3 AND PSAL_QC/PRES_QC>=3 ==> flag 1 because they are corrected
            data_file2['DOXY_ADJUSTED_QC'][:] = np.where(mask, b'1', data_file2["DOXY_ADJUSTED_QC"][:])

            # Apply the correction
            data_file2["DOXY_ADJUSTED"][:] = data_file2["DOXY"][:] * coef_kept.gain.value
            if coef_kept.drift is not None:
                data_file2["DOXY_ADJUSTED"][:] = data_file2["DOXY_ADJUSTED"][:] * (
                            1 + coef_kept.drift.value / 100 * delta_T_Ref[:, np.newaxis] / 365)

            # DOXY_ADJUSTED must be FillValue when DOXY is fillvalue and when QC is 4 or 9..
            data_file2["DOXY_ADJUSTED"][:] = np.where(
                data_file2['DOXY'][:].mask,
                data_file2["DOXY"]._FillValue,
                data_file2["DOXY_ADJUSTED"][:]
            )
            mask = np.isin(data_file2['DOXY_ADJUSTED_QC'][:].data, [b'4', b'9'])
            data_file2['DOXY_ADJUSTED'][:] = np.where(mask, data_file2["DOXY_ADJUSTED"]._FillValue,
                                                      data_file2["DOXY_ADJUSTED"][:])

            # DOXY_ADJUSTED_ERROR
            data_file2["DOXY_ADJUSTED_ERROR"][:] = data_file2["DOXY_ADJUSTED"][:] * relative_error / 100
            data_file2["DOXY_ADJUSTED_ERROR"][:] = np.where(
                data_file2['DOXY_ADJUSTED'][:].mask,
                data_file2["DOXY_ADJUSTED_ERROR"]._FillValue,
                data_file2["DOXY_ADJUSTED_ERROR"][:]
            )

            # Global profile QC
            for i_prof in range(0, nb_prof):
                doxy_qc_en_cours = data_file2['DOXY_ADJUSTED_QC'][i_prof]
                good_count = np.isin(doxy_qc_en_cours, good_flags).sum()
                bad_count = np.isin(doxy_qc_en_cours, bad_flags).sum()
                total = good_count + bad_count  # flag 0 and 9 are ignored
                if total != 0:
                    if good_count == total:  # Tous les DOXY_QC sont bons
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b'A'
                    elif good_count / total >= 0.75:  # 75% des DOXY_QC sont bons
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b'B'
                    elif good_count / total >= 0.5:  # 50% des DOXY_QC sont bons
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b'C'
                    elif good_count / total >= 0.25:  # 25% des DOXY_QC sont bons
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b'D'
                    elif good_count / total > 0:  # moins de 25% des DOXY_QC sont bons
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b'E'
                    else:
                        data_file2['PROFILE_DOXY_QC'][i_prof] = b' '  # b'F' ?

            data_file2.close()  # This generate the final file
            data_file.close()
            # Remove the input file and rename the output file with argo convetion.
            Path(res_file).unlink()
            dirname = Path(res_file2).parent
            basename = Path(res_file2).name
            newname = Path(dirname) / ("BD" + basename[2:].replace("_new2.nc",
                                                                   ".nc"))  # os.path.join(dirname,"BD" + basename[2:].replace("_new2.nc", ".nc"))
            Path(res_file2).rename(newname)  # os.rename(res_file2,newname)
            print(f"File {newname} created")
