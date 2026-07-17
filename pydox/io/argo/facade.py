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

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParameterSet
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
from pydox.reporting.utils import fig_commit


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
    uid: Optional[str] = None,
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
    # Appending the uid_suff will allow to identify similar plots created with higher level different configs.

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
        Sprof, min_pres, max_pres, debug_plot=debug_plot, uid=uid
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
        suptitle = "Rtraj data after code selection and cycle matching"
        v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
        fig, ax = plt.subplots(
            nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
        )
        ax = ax.flatten()
        for ii, v in enumerate(v2plot):
            Rtraj_inair[v].plot.line("s-", linewidth=0.5, label="In-Air", ax=ax[ii])
            Rtraj_inwater[v].plot.line(".-", linewidth=0.5, label="In-Water", ax=ax[ii])
            ax[ii].legend()
            ax[ii].grid()
            ax[ii].set_title(f"{v}")
        plt.suptitle(suptitle)
        plt.tight_layout()
        fig_commit(fig, name=suptitle, config_uid=uid)

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
        suptitle = "In-air and In-Water Rtraj data after median-per-cycle grouping"
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
        plt.suptitle(suptitle)
        plt.tight_layout()
        fig_commit(fig, name=suptitle, config_uid=uid)

    if debug_plot:
        # Super-impose Sprof data:
        suptitle = "Sprof vs Rtraj In-Air and In-Water data"
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
        plt.suptitle(suptitle)
        plt.tight_layout()
        fig_commit(fig, name=suptitle, config_uid=uid)

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
        suptitle = "Sprof vs Rtraj In-Air and In-Water data - after substitution"
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
        plt.suptitle(suptitle)
        plt.tight_layout()
        fig_commit(fig, name=suptitle, config_uid=uid)

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
            f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles})!"
        )

    values = ds["CYCLE_NUMBER"].values
    cycles = values[np.logical_and(values >= cycle_first, values <= cycle_last)]
    return tuple([int(c) for c in cycles])
