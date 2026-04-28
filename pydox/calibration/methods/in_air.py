from typing import Any, Self, Optional, Callable, Iterable, Annotated, TypedDict
from collections import OrderedDict
from functools import partial
import logging
from copy import deepcopy

import numpy as np
from argopy import ArgoFloat
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


log = logging.getLogger("pydox.calibration.method.in_air")


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
    ds_rtraj: xr.Dataset, cycle: int | list[int], dim: str = "N_MEASUREMENT"
) -> xr.Dataset:
    """Return trajectory measurements from one or more cycle numbers

    Examples
    --------
    ..code-block :: python
        cyc_select(Rtraj_inwater, cycle=10)
    """
    this = deepcopy(ds_rtraj)
    this = this.drop_sel({dim: ds_rtraj[dim][~ds_rtraj["CYCLE_NUMBER"].isin(cycle)]})

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
    dict[str, xr.Dataset]
    """
    # Get values for salinity:

    var_psal = ["PSAL", "PSAL_ADJUSTED"]

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
    """A custom groupby CYCLE_NUMBER that is able to handle some DataArray correctly (according to type and shape)"""

    def median_for_datetime(x: np.array) -> np.array:
        """Get the median from the integer version of the datetime object, convert median back to datetime"""
        y = x.astype(int)
        y = np.median(y)
        return y.astype("datetime64[ns]")

    def custom_median(x, axis="...", vname=None):
        """A custom median function to be passed to func:`xr.Dataset.groupby.reduce()`"""
        try:
            if x.dtype == "datetime64[ns]":
                return median_for_datetime(x)
            else:
                return np.median(
                    x
                )  # .astype(x.dtype)  # not typing improve performance
        except:
            raise ValueError(f"Unsupported data type to be grouped by: {x.dtype}")

    # We work on DataArray one after the other, to be specific about how to handle each:
    ds = ds.set_coords("CYCLE_NUMBER")
    Y = []

    # Sequential method: (quite slow)
    # for v in ds.data_vars:
    #     this = ds[["CYCLE_NUMBER", v]]
    #     y = this.groupby("CYCLE_NUMBER").reduce(custom_median, keep_attrs=True, vname=v)
    #     Y.append(y)

    # Parallel method with multi-threading (much faster):
    def fct(vname: str, ds: xr.Dataset) -> xr.Dataset:
        this = ds[["CYCLE_NUMBER", vname]]
        return this.groupby("CYCLE_NUMBER").reduce(
            custom_median, keep_attrs=True, vname=vname
        )

    Y = mth_run(fct, ds.data_vars, ds)
    this = xr.merge(Y)

    xr_logging(this, "Samples grouped by cycle numbers with a 'median' operator")
    return this


def psal_rtraj_substitute_sprof(Rtraj: xr.Dataset, subs: MultiProfData) -> xr.Dataset:
    ds = deepcopy(Rtraj)
    cyc_substituted = []
    for cyc in ds["CYCLE_NUMBER"]:
        this = subs.loc[{"N_PROF": subs["CYCLE_NUMBER"] == cyc}]

        if len(this["N_PROF"]) == 0:
            log.debug(f"Cycle number {cyc.values} is in Rtraj but not in Sprof !")
            new_value = np.nan
        else:
            # Use data from primary profile:
            # todo: Check if using primary profile in Sprof is always a valid choice
            new_value = this.isel(N_PROF=0).item()
            cyc_substituted.append(cyc.item())

        # Replace Rtraj PSAL data with Sprof PSAL for this cycle:
        ds["PSAL"].loc[{"CYCLE_NUMBER": ds["CYCLE_NUMBER"] == cyc}] = new_value

    if (np.diff(cyc_substituted) == 1).all() and len(cyc_substituted) > 5:
        cyc_txt = f"[{cyc_substituted[0]}, ..., {cyc_substituted[-1]}]"
    else:
        cyc_txt = f"{cyc_substituted}"

    xr_logging(
        ds["PSAL"],
        f"Replaced Rtraj data with Sprof data for 'CYCLE_NUMBER'= {cyc_txt}",
    )
    xr_logging(
        ds,
        f"Replaced Rtraj PSAL data with Sprof PSAL for 'CYCLE_NUMBER'= {cyc_txt}",
    )
    return ds


class ArgoData:

    def __init__(self, wmo: int, **kwargs) -> None:
        self._cfg: Config = deepcopy(kwargs.get("config", do.params))
        self.af: ArgoFloat = ArgoFloat(
            wmo, host=do.get_params("argo.src", config=self._cfg), cache=True
        )
        self._sprof = None
        self._rtraj = None

    @property
    def Sprof(self) -> xr.Dataset:
        if self._sprof is None:
            self._sprof = self.af.open_dataset("Sprof")
        return self._sprof

    @property
    def Rtraj(self) -> xr.Dataset:
        if self._rtraj is None:
            self._rtraj = self.af.open_dataset("Rtraj")
        return self._rtraj

    def semantic_cycle2number(self) -> list[int]:
        """This func is here for dev, should be `params2cycs`"""

        semantic_cycles: int = do.get_params(
            "calibration_parameters.cycles", config=self._cfg
        )

        if semantic_cycles[0] == "first":
            cycle_first = self.Sprof["CYCLE_NUMBER"].min().item()
        elif semantic_cycles[0] in self.Sprof["CYCLE_NUMBER"]:
            cycle_first = semantic_cycles[0]
        else:
            raise NotImplementedError

        if semantic_cycles[-1] == "last":
            cycle_last = self.Sprof["CYCLE_NUMBER"].max().item()
        elif semantic_cycles[-1] in self.Sprof["CYCLE_NUMBER"]:
            cycle_last = semantic_cycles[-1]
        else:
            raise NotImplementedError

        if cycle_last <= cycle_first:
            raise ValueError(
                f"'calibration_parameters.cycles' is poorly set to un-ordered or equal values ({semantic_cycles})!"
            )

        return [cycle_first, cycle_last]

    def data_for_in_air_method(
        self, debug_plot: bool = True
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """Load Argo float data to correct oxygen with atmospheric data

        New implementation adapted from `m_argo_data.get_argo_data_for_NCEP()`
        """

        ############################################################################################
        # Read some parameters

        min_pres: float = do.get_params(
            "argo.in_water_salinity.min_pressure", config=self._cfg
        )
        max_pres: float = do.get_params(
            "argo.in_water_salinity.max_pressure", config=self._cfg
        )
        in_air_codes: list[int] = do.get_params("argo.codes.in_air", config=self._cfg)
        in_water_codes: list[int] = do.get_params(
            "argo.codes.in_water", config=self._cfg
        )
        which_psal: int = do.get_params("argo.use", config=self._cfg)
        cycles_to_use: int = do.get_params(
            "calibration_parameters.cycles", config=self._cfg
        )

        # Other parameters:
        optode_height = self.af.launchconfig["OptodeVerticalPressureOffset_dbar"]

        ############################################################################################
        # Load data and select variables:

        # GDAC Argo data are loaded when accessing 'Sprof' and 'Rtraj' attributes

        # From full xr.DataSet objects, sub-select only variables that we really need to work with:
        Sprof : MultiProfData = parameter_selection_sprof(self.Sprof)
        Rtraj : TrajData = parameter_selection_rtraj(self.Rtraj)

        ############################################################################################
        # Manipulate xr.DataSet objects for convenience:

        # Ensure that "N_PROF" and "N_LEVELS" are dataset variables and coordinates that can be used with drop_sel.
        for d in ["N_PROF", "N_LEVELS"]:
            Sprof[d] = Sprof[d]
        Sprof = Sprof.set_coords("CYCLE_NUMBER")  # Also for CYCLE_NUMBER

        # Ensure that "N_MEASUREMENT" is a dataset variable and a coordinate that can be used with drop_sel:
        Rtraj["N_MEASUREMENT"] = Rtraj["N_MEASUREMENT"]

        ############################################################################################
        # Select cycles to be used:
        # Sprof = Sprof.where(
        #     (Sprof["CYCLE_NUMBER"] >= first_cycle_to_use)
        #     & (Sprof["CYCLE_NUMBER"] <= last_cycle_to_use),
        #     drop=True,
        # )
        # Rtraj = Rtraj.where(
        #     (Rtraj["CYCLE_NUMBER"] >= first_cycle_to_use)
        #     & (Rtraj["CYCLE_NUMBER"] <= last_cycle_to_use),
        #     drop=True,
        # )
        # Sprof["PLATFORM_NUMBER"] = Sprof["PLATFORM_NUMBER"].astype(
        # int
        # )  # The where transform the nan from int to float ...

        ############################################################################################
        # Get P,T,S near surface from Sprof
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
                Rtraj_inwater[v].plot.line(
                    ".-", linewidth=0.5, label="In Water", ax=ax[ii]
                )
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
            log.debug(
                "In-water trajectory PSAL is full of NaNs after group by cycles !"
            )

        if ~Rtraj_inair["TEMP"].isnull().all():
            log.error("In-air trajectory TEMP is full of NaNs after group by cycles !")
            # todo Should we fall back on using TEMP from Sprof ?

        if ~Rtraj_inwater["TEMP"].isnull().all():
            log.error(
                "In-water trajectory TEMP is full of NaNs after group by cycles !"
            )
            # todo Should we fall back on using TEMP from Sprof ?

        if debug_plot:
            v2plot = ["PSAL", "TEMP", "PPOX_DOXY"]
            fig, ax = plt.subplots(
                nrows=len(v2plot), ncols=1, figsize=(10, 10), dpi=90, sharex=True
            )
            ax = ax.flatten()
            for ii, v in enumerate(v2plot):
                Rtraj_inair[v].plot.line("s-", linewidth=0.5, label="In Air", ax=ax[ii])
                Rtraj_inwater[v].plot.line(
                    ".-", linewidth=0.5, label="In Water", ax=ax[ii]
                )
                ax[ii].legend()
                ax[ii].grid()
                ax[ii].set_title(f"{v}")
            plt.suptitle(
                f"In-air and in-water Rtraj data after median-per-cycle grouping"
            )
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

        # We create a new dataset to avoid any confusion, since we now mix Sprof and Rtraj data:
        # (Here we substitute salinity from Sprof, but it could be possible to extend this to use salinity
        # from a climatology)
        ds_inair = psal_rtraj_substitute_sprof(Rtraj_inair, lut[which_psal])
        ds_inwater = psal_rtraj_substitute_sprof(Rtraj_inwater, lut[which_psal])

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


class MethodInAir(Method):
    rcgroup = "in_air"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if we have everything we need in the configuration to run the method:
        # Check reference data access: or is this to be done when loading data ?
        ...
        # Check something else ?
        ...

    def _repr_params(self) -> list[str]:
        """Return a description of parameters for the 'in_air' method"""
        summary = []
        for param in ["carryover"]:
            value = self._mparam(param)
            summary += [f"  {param}: {format_value_txt(value)}"]

        [summary.append(line) for line in self._repr_dataset()]

        return summary

    def _flatten_configs(self) -> ConfigsDict:
        """Define the entire configuration space to explore with the 'in_air' method"""
        configs: ConfigsDict = OrderedDict()
        icfg: int = 0
        for fit_drift in to_list(self._sparam("fit_drift")):
            for carryover in to_list(self._mparam("carryover")):
                for ds in to_list(self._mparam("dataset")):
                    p: ParameterSet = ParamsInAir(
                        fit_drift=fit_drift,
                        cycles=self._sparam("cycles"),
                        initial_gain=Data(self._sparam("initial_guess.gain"), 0.0),
                        initial_drift=Data(self._sparam("initial_guess.drift"), 0.0),
                        carryover=carryover,
                        dataset=ds,
                        src=self._mparam(f"data.{ds}.src"),
                        dummy=icfg
                        + 1000,  # For dev. to track config number down to coefs results
                    )
                    configs[icfg] = p
                    icfg += 1
        return configs

    def fit(self, a_float: ArgoData, method: ExecutionMethods = "thread") -> Self:
        """Compute calibration coefficients for all possible configuration set and one Argo float

        According to instance configurations (self.configs), this method is in charge of:
        - Loading/preprocessing Argo Float data,
        - Loading/preprocessing Reference data (eg: from NCEP),
        - Executing all possible computations, sequentially or in parallel

        All of these steps are delegated to external functions taking `argofloat_obj` and a :class:`ParameterSet` (ie one value from `self.configs`) as input.

        Parameters
        ----------
        argofloat_obj
            An object that will be able to return Argo float data
            #Todo: define clearly what we expect here

        method: ExecutionMethods

        Returns
        -------
        Self

        """

        # We first need to load data that will be used to fit:
        # Data are loaded BEFORE fit to be shared with all concurrent computations
        input_data = {}

        # Load Argo float data:
        data = a_float.data_for_in_air_method()
        input_data["PPOX1"] = data["ds_inair"]["PPOX_DOXY"].values
        input_data["PPOX2"] = data["ds_inwater"]["PPOX_DOXY"].values

        # Load atmospheric reference data:
        if self._mparam("dataset") == "ncep":
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
            input_data["PPOX1"] = a_float["PPOX1"]
            input_data["PPOX2"] = a_float["PPOX2"]

            # print(
            #     f"Loaded {self._mparam('data.ncep.name')} data from src={self._mparam('data.ncep.src')}"
            # )
            input_data["REF_PPOX"] = np.random.random_sample(
                (len(input_data["PPOX1"]),)
            )  # Dummy

        else:
            raise NotImplementedError(f"dataset={self._mparam('dataset')}")

        # Execute all computations, argument 'method' determines how to do it:
        # 'sequential': one after the other
        # 'thread'/'process' or a Dask client: in parallel
        fct = partial(inair_fit, data=input_data)
        items = [(iset, params) for iset, params in self.configs.items()]

        results: FitResults = compute_fits(items, fct, method=method)

        # compute_fits([], lambda x: x, method=method)

        # Gather more detailed results in dedicated placeholders of the instance:
        for iset, result in results.items():
            self._coefs[iset]: CoefficientsInAir = result.coefs
            self._fit_data[iset] = result.fit_data

            # Possibly add more data:
            self._fit_data[iset]["cycle_bounds"] = params2cycs(
                self.configs[iset], a_float
            )

        # Update fitted status:
        self._fitted = True
        self._fitted_float = {
            "WMO": a_float["WMO"],
            "CYCLE_NUMBER": params2cycs(self.configs[0], a_float),
            # self.configs[*].cycles are all the same
        }
        return self
