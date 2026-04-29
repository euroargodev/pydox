import logging
from copy import deepcopy

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import argopy as ar

import pydox as do
from pydox._config.config import Config
from pydox.utils.compute import mth_run
from pydox.utils.xarray import xr_append_history
from pydox.commodities import ParameterSet
from pydox.io.argo.types import MultiProfData, TrajData


log = logging.getLogger("pydox.io.argo.utils")


def xr_logging(
    obj: xr.Dataset | xr.DataArray, new_entry: str | list[str] = None
) -> xr.Dataset | xr.DataArray:
    """Log entry into a specific attribute of a xarray object"""
    # log.info(new_entry)
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
    """Return trajectory measurements for one or more cycle numbers

    Examples
    --------
    ..code-block :: python
        cyc_select(Rtraj_inwater, cycle=10)
        cyc_select(Rtraj_inwater, cycle=[1,2,3,4,5])

        # Works also with Sprof, just use the appropriate 'dim' argument:
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
    """Convert a cycle range to a list of cycle numbers, handle semantic like 'first' and 'last'

    Parameters
    ----------
    input
    a_float

    Returns
    -------
    list[int]
    """
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
