"""
This module implement the logic to load and process Argo data.

These functions are expected to receive low-level setting values (no high-level object like the configuration).
"""

import logging
from copy import deepcopy

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import argopy as ar

from pydox.io.argo.types import MultiProfData, TrajData
from pydox.io.argo.utils import (
    cycle_select,
    get_ts_near_surface,
    code_select,
    traj_groupby_cycles,
    psal_rtraj_substitute_sprof,
)

log = logging.getLogger("pydox.io.argo.spec")


def _get_argo_data_for_in_air_method(
    min_pres: float,
    max_pres: float,
    in_air_codes: tuple[int, ...],
    in_water_codes: tuple[int, ...],
    which_psal: int,
    cycles: tuple[int, ...],
    Sprof: MultiProfData,
    Rtraj: TrajData,
    debug_plot: bool = False,
) -> dict[str, xr.Dataset | list[int]]:
    """

    Parameters
    ----------
    min_pres
    max_pres
    in_air_codes
    in_water_codes
    which_psal
    cycles
    Sprof
    Rtraj
    debug_plot

    Returns
    -------

    """

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
    Rtraj_inair = code_select(Rtraj, in_air_codes)
    Rtraj_inwater = code_select(Rtraj, in_water_codes)

    # Check NaN:
    for ds, dsname in [(Rtraj_inair, 'in-air'), (Rtraj_inwater, 'in-water')]:
        for pname in ['PSAL', 'TEMP']:
            if ~ds[pname].isnull().all():
                log.debug(f"{dsname.title()} trajectory {pname} DataArray is full of NaNs !")

    #############
    # Then we sub-select measurements for cycle numbers found in in-air and in-water dataset:
    shared_cycles = np.intersect1d(
        Rtraj_inair["CYCLE_NUMBER"], Rtraj_inwater["CYCLE_NUMBER"]
    ).tolist()
    Rtraj_inair = cycle_select(Rtraj_inair, shared_cycles)
    Rtraj_inwater = cycle_select(Rtraj_inwater, shared_cycles)

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
    Rtraj_inair = traj_groupby_cycles(Rtraj_inair)
    Rtraj_inwater = traj_groupby_cycles(Rtraj_inwater)

    # Check NaN:
    # todo Should we fall back on using TEMP from Sprof if Rtraj['TEMP'] is full of NaNs ?
    for ds, dsname in [(Rtraj_inair, 'in-air'), (Rtraj_inwater, 'in-water')]:
        for pname in ['PSAL', 'TEMP']:
            if ~ds[pname].isnull().all():
                log.debug(f"{dsname.title()} trajectory {pname} DataArray is full of NaNs after group by cycles !")

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

    # Lookup table to match with `which_psal` configuration parameter
    lut = {
        1: sprof_near_surf["psal"],
        2: sprof_near_surf["psal_adj"],
        3: sprof_near_surf["psal_merged"],
    }

    # We create new datasets to avoid any confusion, since we now mix Sprof and Rtraj data:
    # (Here we substitute salinity from Sprof, but it could be possible to extend this to use salinity
    # from a climatology)
    ds_inair = deepcopy(Rtraj_inair)
    ds_inwater = deepcopy(Rtraj_inwater)

    ds_inair["PSAL"] = psal_rtraj_substitute_sprof(ds_inair["PSAL"], lut[which_psal])
    ds_inwater["PSAL"] = psal_rtraj_substitute_sprof(
        ds_inwater["PSAL"], lut[which_psal]
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
    for cyc in ds_inair["CYCLE_NUMBER"]:

        t_traj = (
            ds_inair["TEMP"]
            .loc[{"CYCLE_NUMBER": ds_inair["CYCLE_NUMBER"] == cyc}]
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
            log.debug(
                f"Cycle {cyc.item()}: temperature from Rtraj in-air and Sprof differ by more than 0.5 degC ({t_traj - t_sprof:0.2f} degC) !"
            )

    #############
    # Then we affect a correct position to each cycle
    # Because for some ARGOS float (with Iridium Position, not GPS), the position are recalculated.
    # So, it's better to take the position from the Sprof file, where the position ar OK.

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

        for ds in [ds_inwater, ds_inwater]:
            for pname, pvalue in [
                ("LATITUDE", lat),
                ("LONGITUDE", lon),
                ("POSITION_QC", pqc),
            ]:
                ds[pname].loc[{"CYCLE_NUMBER": ds["CYCLE_NUMBER"] == cyc}] = pvalue

    ############################################################################################
    # Update dataset attributes to keep track of processing:
    ds_inair.attrs["title"] = (
        f"{ds_inair.attrs['title']} merged with some Sprof multi-profile data"
    )

    # We return a dict:
    return {
        "ds_inair": ds_inair,
        "ds_inwater": ds_inwater,
        "Sprof": Sprof,
        "Rtraj": Rtraj,
        "cycles": cycles,
    }
