"""
This module implement the logic to load and process Argo data.

These functions are expected to receive low-level setting values (no high-level object like the configuration).
"""

from copy import deepcopy
from typing import Literal, Optional

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import argopy as ar

import pydox as do
from pydox._config.config import Config
from pydox.reporting.logs import getLogger
from pydox.commodities import ParameterSet, PlotParams, TPlotParams
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
    dsname: Literal["Sprof"] = "Sprof",
) -> tuple[int, ...]:
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
    tuple[int]
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
            f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles}). It must ordered and increasing"
        )

    values = ds["CYCLE_NUMBER"].values
    cycles = values[np.logical_and(values >= cycle_first, values <= cycle_last)]
    return tuple([int(c) for c in cycles])
