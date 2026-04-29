from typing import Any, Self, Optional, Callable, Iterable, Annotated, TypedDict
from collections import OrderedDict

from functools import partial, lru_cache
import logging
from copy import deepcopy

import numpy as np
import argopy as ar
import xarray as xr
import matplotlib.pyplot as plt

import pydox as do
from pydox._config.config import Config
from pydox.utils.casting import to_list
from pydox.utils.compute import compute_fits, ExecutionMethods, mth_run
from pydox.utils.xarray import xr_append_history
from pydox.commodities import (
    Data,
    ConfigsDict,
    ParameterSet,
    ParamsInAir,
    CoefficientsInAir,
    FitResults,
)
from pydox._config.utils import format_value_txt
from pydox.core.in_air import inair_fit
from pydox.calibration.method import Method
from pydox.calibration.utils import params2cycs


log = logging.getLogger("pydox.calibration.methods.utils")


# Type for a xarray object with dimensions N_PROF and N_LEVELS
MultiProfData = Annotated[
    xr.Dataset | xr.DataArray,
    {"dims": ("N_PROF", "N_LEVELS")},  # Metadata (not enforced by mypy)
]

# Type for a xarray object with dimensions N_MEASUREMENT
TrajData = Annotated[
    xr.Dataset | xr.DataArray,
    {"dims": ("N_MEASUREMENT",)},  # Metadata (not enforced by mypy)
]


def xr_logging(
    obj: xr.Dataset | xr.DataArray, new_entry: str | list[str] = None
) -> xr.Dataset | xr.DataArray:
    """Log entry into a specific attribute of a xarray object"""
    log.debug(new_entry)
    return xr_append_history(obj, new_entry, attr="pydox_history")


def parameter_selection_sprof(this: xr.Dataset) -> MultiProfData:
    """From a Sprof :class:`xr.Dataset` object, sub-select only variables that we really need

    This will make it easier to manipulate dataset
    """
    pkeep = [v for v in this.data_vars if "OXY" in v]
    pkeep.remove("PROFILE_DOXY_QC")
    for p in ["PSAL", "TEMP", "PRES"]:
        pkeep.append(f"{p}")
        for e in ["QC", "ADJUSTED", "ADJUSTED_QC"]:
            pkeep.append(f"{p}_{e}")

    for p in [
        "JULD",
        "JULD_QC",
        "CYCLE_NUMBER",
        "PLATFORM_NUMBER",
        "LATITUDE",
        "LONGITUDE",
        "POSITION_QC",
    ]:
        pkeep.append(f"{p}")

    # Ensure that "N_PROF" and "N_LEVELS" are dataset variables and coordinates that can be used with drop_sel.
    for d in ["N_PROF", "N_LEVELS"]:
        this[d] = this[d]
    this = this.set_coords("CYCLE_NUMBER")  # Also for CYCLE_NUMBER

    xr_logging(this, "Cherry-pick parameters in Sprof")

    return this[pkeep]


def parameter_selection_rtraj(this: xr.Dataset) -> TrajData:
    """From a Rtraj :class:`xr.Dataset` object, sub-select only variables that we really need

    This will make it easier to manipulate dataset
    """
    pkeep = [v for v in this.data_vars if "OXY" in v]
    for p in ["PSAL", "TEMP", "PRES"]:
        pkeep.append(f"{p}")
        for e in ["QC", "ADJUSTED", "ADJUSTED_QC"]:
            pkeep.append(f"{p}_{e}")

    for p in [
        "JULD",
        "JULD_QC",
        "CYCLE_NUMBER",
        "PLATFORM_NUMBER",
        "LATITUDE",
        "LONGITUDE",
        "POSITION_QC",
    ]:
        pkeep.append(f"{p}")

    for p in [
        "MEASUREMENT_CODE",
        "CYCLE_NUMBER_ADJUSTED",
        "LATITUDE",
        "LONGITUDE",
        "POSITION_QC",
    ]:  # , 'CYCLE_NUMBER_INDEX', 'CYCLE_NUMBER_INDEX_ADJUSTED']:
        pkeep.append(p)

    # todo: we should be careful in using CYCLE_NUMBER_ADJUSTED when available ...

    # Ensure that "N_MEASUREMENT" is a dataset variable and a coordinate that can be used with drop_sel:
    for d in ["N_MEASUREMENT"]:
        this[d] = this[d]
    this = this.set_coords("CYCLE_NUMBER")  # Also for CYCLE_NUMBER

    xr_logging(this, "Cherry-pick parameters in Rtraj")
    return this[pkeep]


def code_select(
    ds_rtraj: xr.Dataset, code: int | list[int], dim: str = "N_MEASUREMENT"
) -> xr.Dataset:
    """Return trajectory measurements from one or more measurement codes

    We don't use 'where' because it does not preserve data types, use drop_sel/drop_isel instead

    Examples
    --------
    ..code-block :: python
        code_select(Rtraj_inwater, code=in_air_codes)
    """
    this = deepcopy(ds_rtraj)
    this = this.drop_sel({dim: ds_rtraj[dim][~ds_rtraj["MEASUREMENT_CODE"].isin(code)]})
    xr_logging(this, f"Select {dim} indexes for specific 'MEASUREMENT_CODE'={code}")
    return this


def cycle_select(
    ds: xr.Dataset, cycle: int | list[int], dim: str = "N_MEASUREMENT"
) -> xr.Dataset:
    """Return trajectory measurements from one or more cycle numbers

    Examples
    --------
    ..code-block :: python
        cyc_select(Rtraj_inwater, cycle=10)

        # Works also with Sprof:
        cyc_select(Sprof, cycle=10, dim='N_PROF')
    """
    this = deepcopy(ds)
    this = this.drop_sel({dim: ds[dim][~ds["CYCLE_NUMBER"].isin(cycle)]})

    if (np.diff(cycle) == 1).all() and len(cycle) > 5:
        cyc_txt = f"[{cycle[0]}, ..., {cycle[-1]}]"
    else:
        cyc_txt = f"{cycle}"
    xr_logging(this, f"Select {dim} indexes for specific 'CYCLE_NUMBER'={cyc_txt}")
    return this


def load_param(parray: xr.DataArray, valid_pres) -> xr.DataArray:  # (N_PROF, )
    """
    todo: This method should be renamed

    Parameters
    ----------
    parray
    valid_pres

    Returns
    -------

    """
    min_pres_idx = valid_pres.argmin(
        dim="N_LEVELS"
    )  # Indices associated to the minimum correct pressure
    pvalue = parray.isel(N_LEVELS=min_pres_idx)
    pvalue = pvalue.where(valid_pres.min(dim="N_LEVELS") != np.inf)
    return pvalue


def get_psal_in_pres_range(
    Sprof: xr.Dataset, min_pres: float, max_pres: float, pname: str = "PSAL"
) -> xr.DataArray:  # (N_PROF, )
    # Get valid pressure levels:
    valid_pres_range = (Sprof["PRES"] >= min_pres) & (
        Sprof["PRES"] <= max_pres
    )  # (N_PROF, N_LEVELS)
    # todo: why not using PRES_ADJUSTED if available ?

    # Get valid measurements:
    valid_qc = (Sprof[f"{pname}_QC"] == 1) | (
        Sprof[f"{pname}_QC"] == 2
    )  # (N_PROF, N_LEVELS)
    # todo: why don't we use flag values from do.get_params('argo.qcflags.psal') ?

    # Mask
    valid_mask = valid_qc & valid_pres_range  # (N_PROF, N_LEVELS)
    valid_pres = Sprof["PRES"].where(valid_mask, other=np.inf)  # (N_PROF, N_LEVELS)

    # For each profile, get the index of the minimum correct pressure:
    min_pres_idx = valid_pres.argmin(dim="N_LEVELS")  # (N_PROF, )

    # Finally get the parameter first valid measurement in the given pressure range:
    pvalue = Sprof[pname].isel(N_LEVELS=min_pres_idx)
    pvalue = pvalue.where(valid_pres.min(dim="N_LEVELS") != np.inf)

    return pvalue


def get_temp_in_pres_range(
    Sprof: xr.Dataset, min_pres: float, max_pres: float, pname: str = "TEMP"
) -> xr.DataArray:  # (N_PROF, )
    """
    # Attention : In Rtraj, all TEMP_QC = 3
    # The Sprof contains TEMP for the profile and the near surface.
    # TEMP_ADJUSTED doesn't contain the near surface data (it's empty)
    # We work on TEMP
    """
    # Get valid pressure levels:
    valid_pres_range = (Sprof["PRES"] >= min_pres) & (
        Sprof["PRES"] <= max_pres
    )  # (N_PROF, N_LEVELS)
    # todo: why not using PRES_ADJUSTED if available ?

    # Get valid measurements:
    valid_qc = (
        (Sprof["TEMP_QC"] == 1) | (Sprof["TEMP_QC"] == 2) | (Sprof["TEMP_QC"] == 3)
    )  # (N_PROF, N_LEVELS)
    # todo: why don't we use flag values from do.get_params('argo.qcflags.temp') ?

    # Mask
    valid_mask = valid_qc & valid_pres_range  # (N_PROF, N_LEVELS)
    valid_pres = Sprof["PRES"].where(valid_mask, other=np.inf)  # (N_PROF, N_LEVELS)

    # For each profile, get the index of the minimum correct pressure:
    min_pres_idx = valid_pres.argmin(dim="N_LEVELS")  # (N_PROF, )

    # Finally get the parameter first valid measurement in the given pressure range:
    pvalue = Sprof[pname].isel(N_LEVELS=min_pres_idx)
    pvalue = pvalue.where(valid_pres.min(dim="N_LEVELS") != np.inf)

    return pvalue


def get_ts_near_surface(
    Sprof: xr.Dataset, min_pres: float, max_pres: float, debug_plot: bool = False
) -> dict[str, xr.DataArray]:
    """Load salinity and temperature near the surface from Sprof data

    Parameters
    ----------
    Sprof
    min_pres
    max_pres
    debug_plot

    Returns
    -------
    dict[str, xr.DataArray]
    """
    # Get values for salinity:

    var_psal = ["PSAL", "PSAL_ADJUSTED"]
    spsal, spsal_adj = None, None

    for i_var in range(0, len(var_psal)):
        pname = var_psal[i_var]  # (N_PROF, N_LEVELS)
        log.debug(
            f"Look for {pname} in Sprof near the surface between {min_pres} and {max_pres}"
        )
        pvalue = get_psal_in_pres_range(Sprof, min_pres, max_pres, pname)

        # Extract associated PSAL (good QC and good pressure)
        if i_var == 0:
            spsal = pvalue.copy()  # (N_PROF, )
        else:
            spsal_adj = pvalue.copy()  # (N_PROF, )

    # Merge psal_adj with psal
    # (keep values from psal_adj when available and those from psal when psal_adj is null)
    spsal_merged = spsal_adj.copy().rename("PSAL_MERGED")
    spsal_merged[spsal_adj.isnull()] = spsal[spsal_adj.isnull()]

    if debug_plot:
        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 4), dpi=90, sharex=True)
        markers = ["s", "*", "."]
        for ii, ds in enumerate([spsal, spsal_adj, spsal_merged]):
            ds.plot.line("-", linewidth=0.5, ax=ax, label=ds.name, marker=markers[ii])
        plt.grid()
        plt.legend()
        plt.title("Near-surface salinity from Sprof")
        plt.tight_layout()
        plt.show()

    # Then get values for temperature:
    stemp = get_temp_in_pres_range(Sprof, min_pres, max_pres, "TEMP")

    if debug_plot:
        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 4), dpi=90, sharex=True)
        stemp.plot.line("s-", linewidth=0.5, ax=ax, label=stemp.name)
        plt.grid()
        plt.legend()
        plt.title("Near-surface temperature from Sprof")
        plt.tight_layout()
        plt.show()

    return {
        "psal": spsal,
        "psal_adj": spsal_adj,
        "psal_merged": spsal_merged,
        "temp": stemp,
    }


def traj_groupby_cycles(ds: xr.Dataset) -> xr.Dataset:
    """A custom groupby CYCLE_NUMBER for Traj dataset that is able to handle data types correctly

    Data types supported: int, float and datetime64
    """
    # Read type of input variables:
    dtypes = {}
    [dtypes.update({v: ds[v].dtype}) for v in ds]

    # Convert all datetime64 to integers:
    for v in ds.data_vars:
        if ds[v].dtype == "datetime64[ns]":
            ds[v] = ds[v].astype(int)

    # Apply groupby reduction with a median:
    this = ds.groupby("CYCLE_NUMBER").median(keep_attrs=True)

    # Make sure data types are conserved:
    # (groupby.median tends to return only float64)
    for v in ds:
        if v in this and this[v].dtype != dtypes[v]:
            # log.debug(f"Convert {v} from {this[v].dtype} to {dtypes[v]}")
            this[v] = this[v].astype(dtypes[v])

    #
    xr_logging(this, "Samples grouped by cycle numbers with a 'median' operator")
    return this


def psal_rtraj_substitute_sprof(
    Rtraj_psal: xr.DataArray, subs: xr.DataArray
) -> xr.DataArray:
    da = deepcopy(Rtraj_psal)

    # Read values to substitute
    cyc_substituted: list[int] = []

    def fct(
        cyc: xr.DataArray, subs: xr.DataArray, cyc_substituted: list[int]
    ) -> tuple[int, float]:
        this = subs.loc[{"N_PROF": subs["CYCLE_NUMBER"] == cyc}]

        if len(this["N_PROF"]) == 0:
            log.debug(f"Cycle number {cyc.values} is in Rtraj but not in Sprof !")
            new_value = np.nan
        else:
            # Use data from primary profile:
            # todo: Check if using primary profile in Sprof is always a valid choice
            new_value = this.isel(N_PROF=0).item()
            cyc_substituted.append(cyc.item())

        return cyc.item(), new_value

    # (parallel implementation with multi-threading, faster than a naive sequential):
    Y = mth_run(fct, da["CYCLE_NUMBER"], subs, cyc_substituted)

    # Replace Rtraj PSAL data with Sprof PSAL for each cycle:
    for cyc, new_value in Y:
        ii = da["CYCLE_NUMBER"] == cyc
        da.loc[{"CYCLE_NUMBER": ii}] = new_value
    #
    if (np.diff(cyc_substituted) == 1).all() and len(cyc_substituted) > 5:
        cyc_txt = f"[{cyc_substituted[0]}, ..., {cyc_substituted[-1]}]"
    else:
        cyc_txt = f"{cyc_substituted}"

    xr_logging(
        da,
        f"Replaced Rtraj PSAL data with Sprof PSAL for 'CYCLE_NUMBER'= {cyc_txt}",
    )
    return da


def semantic_cycle2values(
    input: Config | ParameterSet, a_float: ar.ArgoFloat
) -> list[int]:
    Sprof: xr.Dataset = a_float.dataset("Sprof")

    try:
        semantic_cycles: tuple = do.get_params(
            "calibration_parameters.cycles", config=input
        )
    except Exception as e:
        if isinstance(input, ParameterSet):
            semantic_cycles: tuple = input.cycles
        else:
            raise e

    if semantic_cycles[0] == "first":
        cycle_first = Sprof["CYCLE_NUMBER"].min().item()
    elif semantic_cycles[0] in Sprof["CYCLE_NUMBER"]:
        cycle_first = semantic_cycles[0]
    else:
        raise NotImplementedError(
            f"Unsupported value for calibration_parameters.cycles[0]: '{semantic_cycles[0]}'"
        )

    if semantic_cycles[-1] == "last":
        cycle_last = Sprof["CYCLE_NUMBER"].max().item()
    elif semantic_cycles[-1] in Sprof["CYCLE_NUMBER"]:
        cycle_last = semantic_cycles[-1]
    else:
        raise NotImplementedError(
            f"Unsupported value for calibration_parameters.cycles[-1]: '{semantic_cycles[-1]}'"
        )

    if cycle_last <= cycle_first:
        raise ValueError(
            f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles})!"
        )

    values = Sprof["CYCLE_NUMBER"].values
    cycles = values[np.logical_and(values >= cycle_first, values <= cycle_last)]
    return [int(c) for c in cycles]


def _get_argo_data_for_in_air_method(
    min_pres: float,
    max_pres: float,
    in_air_codes: tuple[int],
    in_water_codes: tuple[int],
    which_psal: int,
    cycles: tuple[int],
    Sprof: MultiProfData,
    Rtraj: TrajData,
    debug_plot: bool = False,
):
    ############################################################################################
    # Manipulate xr.DataSet objects for convenience:

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

    if ~Rtraj_inair["PSAL"].isnull().all():
        log.debug("In-air trajectory PSAL is full of NaNs !")

    if ~Rtraj_inwater["PSAL"].isnull().all():
        log.debug("In-water trajectory PSAL is full of NaNs !")

    if ~Rtraj_inair["TEMP"].isnull().all():
        log.debug("In-air trajectory TEMP is full of NaNs !")

    if ~Rtraj_inwater["TEMP"].isnull().all():
        log.debug("In-water trajectory TEMP is full of NaNs !")

    #############
    # Then we sub-select measurements for overlapping cycle numbers:
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

    if ~Rtraj_inair["PSAL"].isnull().all():
        log.debug("In-air trajectory PSAL is full of NaNs after group by cycles !")

    if ~Rtraj_inwater["PSAL"].isnull().all():
        log.debug("In-water trajectory PSAL is full of NaNs after group by cycles !")

    if ~Rtraj_inair["TEMP"].isnull().all():
        log.error("In-air trajectory TEMP is full of NaNs after group by cycles !")
        # todo Should we fall back on using TEMP from Sprof ?

    if ~Rtraj_inwater["TEMP"].isnull().all():
        log.error("In-water trajectory TEMP is full of NaNs after group by cycles !")
        # todo Should we fall back on using TEMP from Sprof ?

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
    # Then we affect a position to each cycle
    # For some ARGOS float (with Iridium Position, not GPS), the position are recalculated.
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

        ds_inair["LATITUDE"].loc[
            {"CYCLE_NUMBER": ds_inair["CYCLE_NUMBER"] == cyc}
        ] = lat
        ds_inair["LONGITUDE"].loc[
            {"CYCLE_NUMBER": ds_inair["CYCLE_NUMBER"] == cyc}
        ] = lon
        ds_inair["POSITION_QC"].loc[
            {"CYCLE_NUMBER": ds_inair["CYCLE_NUMBER"] == cyc}
        ] = pqc

        ds_inwater["LATITUDE"].loc[
            {"CYCLE_NUMBER": ds_inwater["CYCLE_NUMBER"] == cyc}
        ] = lat
        ds_inwater["LONGITUDE"].loc[
            {"CYCLE_NUMBER": ds_inwater["CYCLE_NUMBER"] == cyc}
        ] = lon
        ds_inwater["POSITION_QC"].loc[
            {"CYCLE_NUMBER": ds_inwater["CYCLE_NUMBER"] == cyc}
        ] = pqc

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
    }


def get_argo_data_for_in_air_method(
    a_float: ar.ArgoFloat,
    config: Config,
    params: Optional[ParameterSet] = None,
    debug_plot: bool = False,
) -> dict[str, xr.Dataset]:
    """Load Argo float data to correct oxygen with atmospheric data

    We load data from all cycle numbers and cache results.

    New implementation adapted from `m_argo_data.get_argo_data_for_NCEP()`
    """

    ############################################################################################
    # Read some parameters from the Config:

    min_pres: float = do.get_params(
        "argo.in_water_salinity.min_pressure", config=config
    )
    max_pres: float = do.get_params(
        "argo.in_water_salinity.max_pressure", config=config
    )
    in_air_codes: list[int] = do.get_params("argo.codes.in_air", config=config)
    in_water_codes: list[int] = do.get_params("argo.codes.in_water", config=config)
    which_psal: int = do.get_params("argo.use", config=config)

    # Read other parameters from the ParameterSet:
    if params is None:
        cycles: list[int] = semantic_cycle2values(input=config, a_float=a_float)
    else:
        cycles: list[int] = semantic_cycle2values(input=params, a_float=a_float)

    # Read parameters from the ar.ArgoFloat:
    # optode_height: float = a_float.launchconfig["OptodeVerticalPressureOffset_dbar"]

    ############################################################################################
    # Load data and select variables:

    # GDAC Argo data are loaded when accessing 'Sprof' and 'Rtraj' attributes

    # From full xr.DataSet objects, sub-select only variables that we really need to work with:
    Sprof: MultiProfData = parameter_selection_sprof(a_float.dataset("Sprof"))
    Rtraj: TrajData = parameter_selection_rtraj(a_float.dataset("Rtraj"))

    return _get_argo_data_for_in_air_method(
        min_pres=min_pres,
        max_pres=max_pres,
        in_air_codes=tuple(in_air_codes),
        in_water_codes=tuple(in_water_codes),
        which_psal=which_psal,
        cycles=tuple(cycles),
        Sprof=Sprof,
        Rtraj=Rtraj,
        debug_plot=debug_plot,
    )


def get_atmospheric_data_for_in_air_method(
    argo_data: dict[str, xr.Dataset | Any],
    config: Config,
    params: Optional[ParameterSet] = None,
    debug_plot: bool = False,
):
    """Load atmospheric reference data"""
    dataset: str = do.get_params("calibration_methods.in_air.dataset", config=config)
    data: dict[str, Any] = {}

    if dataset == "ncep":
        # dsair, dsinwater = get_argo_data_for_NCEP(
        #     ds_argo_Rtraj,
        #     ds_argo_Sprof,
        #     which_var,
        #     code_inair,
        #     code_inwater,
        #     min_pres,
        #     max_pres,
        # )

        # PPOX1 = dsair["PPOX_DOXY"].values
        # PPOX2 = dsinwater["PPOX_DOXY"].values

        # Dummy replacement:
        # input_data["PPOX1"] = a_float["PPOX1"]
        # input_data["PPOX2"] = a_float["PPOX2"]

        # print(
        #     f"Loaded {self._mparam('data.ncep.name')} data from src={self._mparam('data.ncep.src')}"
        # )
        data["REF_PPOX"] = np.random.random_sample(
            (len(argo_data["ds_inair"]["PPOX_DOXY"].values),)
        )  # Dummy

    else:
        raise NotImplementedError(f"dataset={dataset}")

    return data
