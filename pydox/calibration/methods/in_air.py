from typing import Any, Self, Optional
from collections import OrderedDict
from functools import partial
import logging

import numpy as np
import pandas as pd
from argopy import ArgoFloat
import xarray as xr
import matplotlib.pyplot as plt

import pydox as do
from pydox.utils.casting import to_list
from pydox.utils.compute import compute_fits, ExecutionMethods
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


# raise ValueError(
#     "I need to determine how to access cycle numbers to work with from with ArgoData.data_for_in_air_method() while it is an input of MethodInAir.fit() ! This indicate that the `input_data` dict passed down to the inair_fit function argument `data` must be resolve within the config loop ?"
# )


def load_param(parray: xr.DataArray, valid_pres) -> xr.DataArray:  # (N_PROF, )
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


def traj_groupby_cycles(ds: xr.Dataset) -> xr.Dataset:
    """A custom groupby CYCLE_NUMBER that is able to handle some DataArray correctly (according to type and shape)"""

    def median_for_strings(x: np.array) -> np.array:
        """Some median estimate for an array of strings

        By default, this return the string that has the median number of occurrences.
        If this is not defined, return the string with the maximum number of occurrences.
        In the scenario where the nb of occurrences is similar for more than one string, return the 1st one.
        """
        unique, counts = np.unique(x, return_counts=True)
        y = unique[counts == np.ceil(np.median(counts))]
        if y.size == 0:
            y = unique[counts == np.max(counts)]
        return y[0].astype(x.dtype)

    def median_for_datetime(x: np.array) -> np.array:
        """Get the median from the integer version of the datetime object, convert median back to datetime"""
        y = x.astype(int)
        y = np.median(y)
        return y.astype("datetime64[ns]")

    def custom_median(x, axis="...", vname=None):
        """A custom median function to be passed to func:`xr.Dataset.groupby.reduce()`"""

        # if vname is not None and vname == 'TRAJECTORY_PARAMETER_DATA_MODE':
        # print(vname, axis, x.shape, len(x.shape), median_for_strings(x).shape)

        if len(x.shape) == 2:
            y = np.array(
                [
                    custom_median(x[:, ii], axis=axis, vname=vname)
                    for ii in range(x.shape[-1])
                ]
            )
            # print(vname, y.shape)

        try:
            return np.median(x).astype(x.dtype)
        except:
            if x.dtype == "datetime64[ns]":
                return median_for_datetime(x)
            if x.dtype == "<U1":
                return median_for_strings(x)
            if x.dtype == "<U3":
                return median_for_strings(x)
        return 9999

    # We work on DataArray one after the other, to be specific about how to handle each:
    ds = ds.set_coords("CYCLE_NUMBER")
    Y = []
    for v in ds.data_vars:
        if "N_MEASUREMENT" in ds[v].dims:
            try:
                if ds[v].dims == ():
                    Y.append(ds[v])
                else:
                    this = ds[["CYCLE_NUMBER", v]]

                    if this[v].dtype in ["datetime64[ns]", "<U1", "<U3"]:
                        if v in ["TRAJECTORY_PARAMETER_DATA_MODE"]:
                            y = this.groupby("CYCLE_NUMBER").reduce(
                                custom_median,
                                dim=this[v].dims,
                                keep_attrs=True,
                                vname=v,
                            )
                        else:
                            y = this.groupby("CYCLE_NUMBER").reduce(
                                custom_median, keep_attrs=True, vname=v
                            )
                    else:
                        y = this.groupby("CYCLE_NUMBER").median(
                            skipna=True, keep_attrs=True
                        )

                    if v not in y:
                        print("😫", v, ds[v].dims, ds[v].dtype)
                    else:
                        Y.append(y)
            except:
                raise
                print("‼️", v, ds[v].dims, ds[v].dtype)
                Y.append(ds[v])
        else:
            Y.append(ds[v])
    return xr.merge(Y)


class ArgoData:

    def __init__(self, wmo: int, **kwargs) -> None:
        self.af = ArgoFloat(wmo, host=do.get_params("argo.src"))

    def data_for_in_air_method(
        self, config, debug_plot: bool = True
    ) -> tuple[xr.Dataset, xr.Dataset]:
        """Load Argo float data to correct oxygen with atmospheric data

        New implementation adapted from `m_argo_data.get_argo_data_for_NCEP()`
        """
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

        Sprof: xr.Dataset = self.af.open_dataset("Sprof")
        Rtraj: xr.Dataset = self.af.open_dataset("Rtraj")
        Rtraj["N_MEASUREMENT"] = Rtraj[
            "N_MEASUREMENT"
        ]  # Just make sure that N_MEASUREMENT is a dataset variable and a coordinate that can be used with drop_sel

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

        valid_pres_range = (Sprof["PRES"] >= min_pres) & (
            Sprof["PRES"] <= max_pres
        )  # (N_PROF, N_LEVELS)
        # todo: why not using PRES_ADJUSTED if available ?

        ############################################################################################
        # Get correct values for PSAL and PSAL_ADJUSTED near the surface

        for pname in ["PSAL", "PSAL_ADJUSTED"]:
            print(
                f"Look for {pname} in Sprof near the surface between {min_pres} and {max_pres}"
            )
            pvalue = get_psal_in_pres_range(Sprof, min_pres, max_pres, pname)

            # Extract associated PSAL (good QC and good pressure)
            if pname == "PSAL":
                psal_results = pvalue.to_numpy()  # (N_PROF, )
            else:
                psal_adj_results = pvalue.to_numpy()  # (N_PROF, )

        # Xarray -> Numpy:
        cycle_results = Sprof["CYCLE_NUMBER"].to_numpy()  # int(N_PROF, )
        psal_mixt_results = np.where(
            np.isnan(psal_adj_results), psal_results, psal_adj_results
        )  # float(N_PROF, )
        # todo: maybe [psal_results, psal_adj_results, psal_mixt_results and cycle_results] could be packaged into a dict.

        if debug_plot:
            plt.figure()
            plt.plot(cycle_results, psal_results, "b.")
            plt.plot(cycle_results, psal_adj_results, "c.")
            plt.plot(cycle_results, psal_mixt_results, "r.")

        ############################################################################################
        # Get correct values for TEMP near the surface

        temp_results = get_temp_in_pres_range(Sprof, min_pres, max_pres, "TEMP")

        ############################################################################################
        # Read INair and INWater data
        # Don't use 'where' because it does not preserve data types, use drop_sel/drop_isel instead

        # Rtraj_inair = Rtraj.where( Rtraj["MEASUREMENT_CODE"].isin(in_air_codes), drop=True )
        # Rtraj_inwater = Rtraj.where(Rtraj["MEASUREMENT_CODE"].isin(in_water_codes), drop=True)

        mask_not_inair = ~Rtraj["MEASUREMENT_CODE"].isin(in_air_codes)
        meas_not_inair = Rtraj["N_MEASUREMENT"][mask_not_inair]
        Rtraj_inair = Rtraj.drop_sel(N_MEASUREMENT=meas_not_inair)

        # or in 1 line:
        # Rtraj_inair = Rtraj.drop_sel(N_MEASUREMENT=Rtraj["N_MEASUREMENT"][~Rtraj["MEASUREMENT_CODE"].isin(in_air_codes)])

        Rtraj_inwater = Rtraj.drop_sel(
            N_MEASUREMENT=Rtraj["N_MEASUREMENT"][
                ~Rtraj["MEASUREMENT_CODE"].isin(in_water_codes)
            ]
        )

        if debug_plot:
            plt.figure()
            Rtraj_inair["TEMP"].plot()
            Rtraj_inwater["TEMP"].plot()

        # When CarryOver is used, we need to mix Inair and Inwater data:
        shared_cycles = xr.DataArray(
            np.intersect1d(Rtraj_inair["CYCLE_NUMBER"], Rtraj_inwater["CYCLE_NUMBER"]),
            dims="N_CYCLE",
        )
        Rtraj_inair = Rtraj_inair.drop_sel(
            N_MEASUREMENT=Rtraj_inair["N_MEASUREMENT"][
                ~Rtraj_inair["CYCLE_NUMBER"].isin(shared_cycles)
            ]
        )
        Rtraj_inwater = Rtraj_inwater.drop_sel(
            N_MEASUREMENT=Rtraj_inwater["N_MEASUREMENT"][
                ~Rtraj_inwater["CYCLE_NUMBER"].isin(shared_cycles)
            ]
        )

        # Reduce measurements by cycle numbers (Median value per cycle):
        Rtraj_inair = traj_groupby_cycles(Rtraj_inair)
        Rtraj_inwater = traj_groupby_cycles(Rtraj_inwater)

        # Replace Rtraj PSAL data with Sprof PSAL because ... ?

        lut = {1: spsal, 2: spsal_adj, 3: spsal_merged}

        for cyc in Rtraj_inair["CYCLE_NUMBER"]:

            this = lut[which_psal]
            this = this.loc[{"N_PROF": this["CYCLE_NUMBER"] == cyc}]

            if len(this["N_PROF"]) == 0:
                print(f"Cycle numner {cyc.values} in Rtraj but not in Sprof !")
                new_value = np.nan
            else:
                new_value = this.item()

            Rtraj_inair["PSAL"].loc[
                {"CYCLE_NUMBER": Rtraj_inair["CYCLE_NUMBER"] == cyc}
            ] = new_value
            Rtraj_inwater["PSAL"].loc[
                {"CYCLE_NUMBER": Rtraj_inwater["CYCLE_NUMBER"] == cyc}
            ] = new_value

            t_traj = (
                Rtraj_inair["TEMP"]
                .loc[{"CYCLE_NUMBER": Rtraj_inair["CYCLE_NUMBER"] == cyc}]
                .item()
            )
            t_sprof = stemp.loc[{"N_PROF": stemp["CYCLE_NUMBER"] == cyc}].item()

            if np.abs(t_traj - t_sprof) > 0.5:
                print(
                    f"Cycle {cyc.item()}: Rtraj Temperature differs by more than 0.5 degC the temperature from Sprof ({t_traj - t_sprof:0.2f} degC)"
                )

        raise ValueError(
            "This is where am I. # We affect a position to each cycle. See also notebook: dev-pr010-ArgoData-02.ipynb"
        )


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
        dsair, dsinwater = a_float.data_for_in_air_method()
        input_data["PPOX1"] = dsair["PPOX_DOXY"].values
        input_data["PPOX2"] = dsinwater["PPOX_DOXY"].values

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
