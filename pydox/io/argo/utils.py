from typing import Optional, Literal
import logging
from copy import deepcopy

import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

from pydox.utils.compute import mth_run
from pydox.utils.xarray import xr_append_history
from pydox.io.argo.types import MultiProfData, TrajData


log = logging.getLogger("pydox.io.argo.utils")


def xr_logging(
    obj: xr.Dataset | xr.DataArray, new_entry: str | list[str] = None
) -> xr.Dataset | xr.DataArray:
    """Log entry into a specific attribute of a xarray object

    This function is used to register what modification we perform on a xr.Dataset or xr.DataArry.

    Parameters
    ----------
    obj: xr.Dataset | xr.DataArray
        Xarray object to log new entry into.
    new_entry: str | list[str]
        The new entry to be added to the `pydox_history` attribute of `obj`. If a list of strings is provided, each item is added as a new entry.

    Returns
    -------
    xr.Dataset | xr.DataArray
        Updated object
    """
    # log.info(new_entry)
    return xr_append_history(obj, new_entry, attr="pydox_history")


def preprocess_raw_sprof(ds_sprof: xr.Dataset) -> MultiProfData:
    """Pre-process a Sprof :class:`xr.Dataset` object for in-air fit computation

    The goal of this function is to make it easier to manipulate the Sprof dataset, within the in-air fit context.

    Processing steps:
    - select only xr.DataArray(s) that we really need
    - convert "N_PROF" and "N_LEVELS" dimensions to variables and coordinates (to be usable with xarray drop_sel)

    Parameters
    ----------
    ds_sprof: xr.Dataset

    Returns
    -------
    MultiProfData | xr.Dataset
        This is a multi-profil :class:`xr.Dataset`, i.e. with `N_PROF` and `N_LEVELS` as dimensions and coordinates
    """
    pkeep = [v for v in ds_sprof.data_vars if "OXY" in v]
    pkeep.remove("PROFILE_DOXY_QC")
    for p in ["PSAL", "TEMP", "PRES"]:
        pkeep.append(p)
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
        pkeep.append(p)

    # Ensure that "N_PROF" and "N_LEVELS" are dataset variables and coordinates that can be used with drop_sel.
    for d in ["N_PROF", "N_LEVELS"]:
        ds_sprof[d] = ds_sprof[d]
    ds_sprof = ds_sprof.set_coords("CYCLE_NUMBER")  # Also for CYCLE_NUMBER

    # Log and return
    xr_logging(ds_sprof, "Pre-process raw Sprof")
    return ds_sprof[pkeep]


def preprocess_raw_rtraj(ds_rtraj: xr.Dataset) -> TrajData:
    """Pre-process a Rtraj :class:`xr.Dataset` object for in-air fit computation

    The goal of this function is to make it easier to manipulate the Rtraj dataset, within the in-air fit context.

    Processing steps:
    - select only xr.DataArray(s) that we really need
    - convert `N_MEASUREMENT` dimension to a variable and coordinate (to be usable with xarray drop_sel)
    - convert `CYCLE_NUMBER` variable to a coordinate (to be usable with xarray drop_sel)

    Parameters
    ----------
    ds_rtraj_sprof: xr.Dataset

    Returns
    -------
    TrajData | xr.Dataset
        This is a trajectory :class:`xr.Dataset`, with `N_MEASUREMENT` as dimension and `CYCLE_NUMBER` as coordinates
    """
    pkeep = [v for v in ds_rtraj.data_vars if "OXY" in v]
    for p in ["PSAL", "TEMP", "PRES"]:
        pkeep.append(p)
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
        pkeep.append(p)

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
        ds_rtraj[d] = ds_rtraj[d]
    ds_rtraj = ds_rtraj.set_coords("CYCLE_NUMBER")  # Also for CYCLE_NUMBER

    # Log and return
    xr_logging(ds_rtraj, "Pre-process raw Rtraj")
    return ds_rtraj[pkeep]


def code_select(
    ds_rtraj: xr.Dataset,
    code: int | list[int],
) -> xr.Dataset:
    """Select trajectory measurements for one or more measurement codes

    Parameters
    ----------
    ds_rtraj: xr.Dataset
        The dataset to work with. Must have `N_MEASUREMENT` as dimension and `MEASUREMENT_CODE` in variables.
    code: int | list[int]
        The unique or list of codes, as integers, to select.

    Returns
    -------
    xr.Dataset

    Examples
    --------
    ..code-block :: python
        code_select(Rtraj_inwater, code=in_air_codes)
    """
    if "MEASUREMENT_CODE" not in ds_rtraj:
        raise ValueError("'MEASUREMENT_CODE' is a mandatory variable for this function")

    this = deepcopy(
        ds_rtraj
    )  # Make sure we do not modify the input data and return a modified deep copy
    this = this.drop_sel(
        {
            "N_MEASUREMENT": ds_rtraj["N_MEASUREMENT"][
                ~ds_rtraj["MEASUREMENT_CODE"].isin(code)
            ]
        }
    )

    # log step:
    xr_logging(
        this, f"Select 'N_MEASUREMENT' indexes for specific 'MEASUREMENT_CODE'={code}"
    )

    #
    return this


def cycle_select(
    ds: xr.Dataset, cycle: int | list[int], dim: str = "N_MEASUREMENT"
) -> xr.Dataset:
    """Select trajectory measurements or multi-profil profiles for one or more cycle numbers

    Parameters
    ----------
    ds: xr.Dataset
        The dataset to work with. Must have `CYCLE_NUMBER` in variables.
    code: int | list[int]
        The unique or list of codes, as integers, to select.
    dim: str, default = "N_MEASUREMENT"
        The dataset dimension to select cycle from. With a trajectory file, this is `N_MEASUREMENT` (default). For a multi-profil file, this is `N_PROF`.

    Returns
    -------
    xr.Dataset

    Examples
    --------
    ..code-block :: python
        cyc_select(Rtraj_inwater, cycle=10)
        cyc_select(Rtraj_inwater, cycle=[1,2,3,4,5])

        # Works also with Sprof, just use the appropriate 'dim' argument:
        cyc_select(Sprof, cycle=10, dim='N_PROF')
    """
    this = deepcopy(
        ds
    )  # Make sure we do not modify the input data and return a modified deep copy
    this = this.drop_sel({dim: ds[dim][~ds["CYCLE_NUMBER"].isin(cycle)]})

    # log step:
    if (np.diff(cycle) == 1).all() and len(cycle) > 5:
        cyc_txt = f"[{cycle[0]}, ..., {cycle[-1]}]"
    else:
        cyc_txt = f"{cycle}"
    xr_logging(this, f"Select {dim} indexes for specific 'CYCLE_NUMBER'={cyc_txt}")

    #
    return this


def get_variable_in_pres_range(
    ds: MultiProfData,
    min_pres: float,
    max_pres: float,
    varname: str,
    mask: Optional[xr.DataArray] = None,
    presname: str = "PRES",
) -> xr.DataArray:  # (N_PROF, )
    """A generic function to select the shallowest values over a pressure range for a given multi-prof dataset variable

    Parameters
    ----------
    ds: xr.Dataset
        The multi-profil dataset to work with, i.e. with (`N_PROF`, `N_LEVELS`) dimensions.
    min_pres: float
        The minimum value (db) of the pressure range to consider.
    max_pres: float
        The maximum value (db) of the pressure range to consider.
    varname: str
        The dataset variable (Argo parameter) to return (i.e. one of the :class:`xr.Dataset.data_vars`).
    presname: str, default='PRES'
        The pressure axis to use. Could be `PRES` or `PRES_ADJUSTED`.
    mask: Optional[xr.DataArray] = None
        A mask to apply for sub-selecting data over the pressure range, typically based on QC values. This is a :class:`xr.DataArray` with dimensions (`N_PROF`, `N_LEVELS`)

    Returns
    -------
    xr.DataArray
        Selected data, with `N_PROF` dimension.

    """
    # Get valid pressure levels:
    prange_mask = (ds[presname] >= min_pres) & (
        ds[presname] <= max_pres
    )  # (N_PROF, N_LEVELS)
    # todo: why not using PRES_ADJUSTED if available ?

    # Mask
    if mask is not None:
        prange_mask = mask & prange_mask  # (N_PROF, N_LEVELS)

    valid_pres = ds[presname].where(prange_mask, other=np.inf)  # (N_PROF, N_LEVELS)

    # For each profile, get the index of the minimum correct pressure:
    min_pres_idx = valid_pres.argmin(dim="N_LEVELS")  # (N_PROF, )

    # Finally get the parameter first valid measurement in the given pressure range:
    da = ds[varname].isel(N_LEVELS=min_pres_idx)
    da = da.where(valid_pres.min(dim="N_LEVELS") != np.inf)

    return da


def get_psal_in_pres_range(
    ds: MultiProfData,
    min_pres: float,
    max_pres: float,
    pname: Literal["PSAL", "PSAL_ADJUSTED"] = "PSAL",
) -> xr.DataArray:  # (N_PROF, )
    """Select the first valid PSAL values over a pressure range in a multi-profil dataset

    Parameters
    ----------
    ds: xr.Dataset
        The multi-profil dataset to work with
    min_pres: float
        The minimum value (db) of the pressure range to consider.
    max_pres: float
        The maximum value (db) of the pressure range to consider.
    pname: str, default="PSAL"
        The Argo parameter to return (i.e. one of the :class:`xr.Dataset.data_vars`).

    Returns
    -------
    xr.DataArray
        Selected data, with `N_PROF` dimension.

    """

    # Get valid measurements:
    valid_qc = (ds[f"{pname}_QC"] == 1) | (ds[f"{pname}_QC"] == 2)  # (N_PROF, N_LEVELS)
    # todo: why don't we use flag values from do.get_params('argo.qcflags.psal') ?

    return get_variable_in_pres_range(
        ds, min_pres, max_pres, varname=pname, mask=valid_qc
    )


def get_temp_in_pres_range(
    ds: MultiProfData, min_pres: float, max_pres: float, pname: str = "TEMP"
) -> xr.DataArray:  # (N_PROF, )
    """Select the first valid TEMP values over a pressure range in a multi-profil dataset

    Parameters
    ----------
    ds: xr.Dataset
        The multi-profil dataset to work with
    min_pres: float
        The minimum value (db) of the pressure range to consider.
    max_pres: float
        The maximum value (db) of the pressure range to consider.
    pname: str, default="TEMP"
        The Argo parameter to return (i.e. one of the :class:`xr.Dataset.data_vars`).

    Returns
    -------
    xr.DataArray
        Selected data, with `N_PROF` dimension.

    Comments
    --------
    Attention : In Rtraj, all TEMP_QC = 3
    The Sprof contains TEMP for the profile and the near surface.
    TEMP_ADJUSTED doesn't contain the near surface data (it's empty)
    We work on TEMP
    """
    # Get valid measurements:
    valid_qc: xr.DataArray = (
        (ds["TEMP_QC"] == 1) | (ds["TEMP_QC"] == 2) | (ds["TEMP_QC"] == 3)
    )  # (N_PROF, N_LEVELS)
    # todo: why don't we use flag values from do.get_params('argo.qcflags.temp') ?

    return get_variable_in_pres_range(
        ds, min_pres, max_pres, varname=pname, mask=valid_qc
    )


def get_ts_near_surface(
    ds_sprof: MultiProfData, min_pres: float, max_pres: float, debug_plot: bool = False
) -> dict[str, xr.DataArray]:
    """Load valid salinity and temperature near the surface from a multi-profil Sprof dataset

    Parameters
    ----------
    ds_sprof: xr.Dataset
        The Sprof multi-profil dataset
    min_pres: float
        The minimum value (db) of the pressure range to consider.
    max_pres: float
        The maximum value (db) of the pressure range to consider.
    debug_plot: bool, default=False

    Returns
    -------
    dict[str, xr.DataArray]
    """
    # Get values for salinity:

    var_psal = ["PSAL", "PSAL_ADJUSTED"]
    spsal, spsal_adj = None, None

    for i_var in range(0, len(var_psal)):
        pname: str = var_psal[i_var]
        log.debug(
            f"Look for {pname} in Sprof near the surface between {min_pres} and {max_pres}"
        )
        # Extract associated PSAL (good QC and good pressure)
        pvalue: xr.DataArray = get_psal_in_pres_range(
            ds_sprof, min_pres, max_pres, pname
        )  # (N_PROF, )

        # Copy to the appropriate variable:
        if i_var == 0:
            spsal: xr.DataArray = pvalue.copy()  # (N_PROF, )
        else:
            spsal_adj: xr.DataArray = pvalue.copy()  # (N_PROF, )

    # Merge psal_adj with psal
    # (keep values from psal_adj when available and those from psal when psal_adj is null)
    spsal_merged: xr.DataArray = spsal_adj.copy().rename("PSAL_MERGED")  # (N_PROF, )
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
    stemp = get_temp_in_pres_range(ds_sprof, min_pres, max_pres, "TEMP")

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
    """A custom group-by CYCLE_NUMBER for a trajectory dataset that is able to handle data types correctly

    Data types supported: int, float and datetime64

    Parameters
    ----------
    ds: xr.Dataset
        The dataset to work with. This must be a trajectory dataset, i.e. with `N_MEASUREMENT`

    Returns
    -------
    xr.Dataset

    """
    # Read data type of input variables:
    dtypes = {}
    [dtypes.update({v: ds[v].dtype}) for v in ds]

    # Convert all datetime64 to integers:
    for v in ds.data_vars:
        if ds[v].dtype == "datetime64[ns]":
            ds[v] = ds[v].astype(int)

    # Apply groupby reduction with a median:
    this = ds.groupby("CYCLE_NUMBER").median(keep_attrs=True)

    # Make sure data types are conserved:
    # (groupby.median tends to return only floats)
    for v in ds:
        if v in this and this[v].dtype != dtypes[v]:
            # log.debug(f"Convert {v} from {this[v].dtype} to {dtypes[v]}")
            this[v] = this[v].astype(dtypes[v])

    #
    xr_logging(this, "Samples grouped by cycle numbers with a 'median' operator")
    return this


def psal_rtraj_substitute_sprof(
    Rtraj_psal: xr.DataArray, Sprof_psal: xr.DataArray
) -> xr.DataArray:
    """Substitute salinity from Rtraj data with those from Sprof data

    It could be possible to extend this to use salinity from a climatology, not Sprof

    Parameters
    ----------
    Rtraj_psal: xr.DataArray
        Trajectory array with `CYCLE_NUMBER` as dimension and `CYCLE_NUMBER` as coordinates.
    Sprof_psal: xr.DataArray
        Synthetic multi-profil array with `N_PROF` as dimension and `CYCLE_NUMBER` as coordinates.

    Returns
    -------
    xr.DataArray
        A deepcopy of Rtraj_psal but with values from Sprof_psal
    """
    if "CYCLE_NUMBER" not in Rtraj_psal.dims:
        raise ValueError  # todo Error message to be completed
    if "CYCLE_NUMBER" not in Rtraj_psal.coords:
        raise ValueError  # todo Error message to be completed
    if "N_PROF" not in Rtraj_psal.dims:
        raise ValueError  # todo Error message to be completed
    if "CYCLE_NUMBER" not in Rtraj_psal.coords:
        raise ValueError  # todo Error message to be completed

    # Make sure we don't modify the input array and work/return a deepcopy:
    da = deepcopy(Rtraj_psal)

    # Read values to substitute from the multi-prof xr.DataArray:
    # (we use a parallel implementation with multi-threading, faster than a naive sequential):
    # The parallelization is done over cycle numbers.
    cyc_substituted: list[int] = []  # A placeholder to keep track of cycle numbers

    def read_new_values(
        trajcyc: xr.DataArray, subs: xr.DataArray, cyc_substituted: list[int]
    ) -> tuple[int, float]:
        this = subs.loc[{"N_PROF": subs["CYCLE_NUMBER"] == trajcyc}]

        if len(this["N_PROF"]) == 0:
            log.debug(
                f"This trajectory array cycle number {trajcyc.values} is not in multi-prof array, replaced with NaN."
            )
            new_value = np.nan
        else:
            # Use data from primary profile:
            # todo: Check if using primary profile in Sprof is always a valid choice
            new_value = this.isel(N_PROF=0).item()
            cyc_substituted.append(trajcyc.item())

        return trajcyc.item(), new_value

    new_values: list[tuple[int, float]] = mth_run(
        read_new_values, da["CYCLE_NUMBER"], Sprof_psal, cyc_substituted
    )

    # Then replace traj data with sprof data, for each cycle:
    for trajcyc, new_value in new_values:
        i_measurements = da["CYCLE_NUMBER"] == trajcyc
        da.loc[{"CYCLE_NUMBER": i_measurements}] = new_value

    # Log and return
    if (np.diff(cyc_substituted) == 1).all() and len(cyc_substituted) > 5:
        cyc_txt = f"[{cyc_substituted[0]}, ..., {cyc_substituted[-1]}]"
    else:
        cyc_txt = f"{cyc_substituted}"

    xr_logging(
        da,
        f"Replaced salinity data from Rtraj with those from Sprof, for 'CYCLE_NUMBER'= {cyc_txt}",
    )
    return da
