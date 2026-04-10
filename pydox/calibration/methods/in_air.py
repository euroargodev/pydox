from typing import Any, Self, Optional
from collections import OrderedDict
from functools import partial
import logging

import numpy as np
import pandas as pd
from argopy import ArgoFloat
import xarray as xr


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


class ArgoData:

    def __init__(self, wmo: int, **kwargs) -> None:
        self.af = ArgoFloat(wmo, host=do.get_params("argo.src"))

    def data_for_in_air_method(self, config) -> tuple[xr.Dataset, xr.Dataset]:
        """Load Argo float data to correct oxygen with atmospheric data

        New implementation from m_argo_data.get_argo_data_for_NCEP()
        """

        min_pres: float = do.get_params("argo.in_water_salinity.min_pressure")
        max_pres: float = do.get_params("argo.in_water_salinity.max_pressure")
        in_air_codes: list[int] = do.get_params("argo.codes.in_air")
        in_water_codes: list[int] = do.get_params("argo.codes.in_water")
        which_psal: int = do.get_params("argo.use")
        first_cycle_to_use: int = do.get_params("calibration_parameters.cycles.first")
        last_cycle_to_use: int = do.get_params("calibration_parameters.cycles.last")

        Sprof: xr.Dataset = self.af.open_dataset("Sprof")
        Rtraj: xr.Dataset = self.af.open_dataset("Rtraj")

        # Select the cycles to be used
        Sprof = Sprof.where(
            (Sprof["CYCLE_NUMBER"] >= first_cycle_to_use)
            & (Sprof["CYCLE_NUMBER"] <= last_cycle_to_use),
            drop=True,
        )
        Rtraj = Rtraj.where(
            (Rtraj["CYCLE_NUMBER"] >= first_cycle_to_use)
            & (Rtraj["CYCLE_NUMBER"] <= last_cycle_to_use),
            drop=True,
        )
        Sprof["PLATFORM_NUMBER"] = Sprof["PLATFORM_NUMBER"].astype(
            int
        )  # The where transform the nan from int to float ...

        valid_pres_range = (Sprof["PRES"] >= min_pres) & (Sprof["PRES"] <= max_pres)
        # todo: why not using PRES_ADJUSTED if available ?

        def load_param(parray: xr.DataArray, valid_pres) -> xr.DataArray:
            min_pres_idx = valid_pres.argmin(
                dim="N_LEVELS"
            )  # Indices associated to the minimum correct pressure
            pvalue = parray.isel(N_LEVELS=min_pres_idx)
            pvalue = pvalue.where(valid_pres.min(dim="N_LEVELS") != np.inf)
            return pvalue

        ############################################################################################
        # Look for (PSAL and PSAL_ADJUSTED) OK nearest from the surface

        var_psal = ["PSAL", "PSAL_ADJUSTED"]

        for i_var in range(0, len(var_psal)):
            var_en_cours = var_psal[i_var]
            log.info(
                f"Look for {var_en_cours} in Sprof near the surface between {min_pres} and {max_pres}"
            )
            valid_qc = (Sprof[f"{var_en_cours}_QC"] == 1) | (
                Sprof[f"{var_en_cours}_QC"] == 2
            )

            # Mask
            valid_mask = valid_qc & valid_pres_range

            # Pressure = Inf if not ok
            valid_pres = Sprof["PRES"].where(valid_mask, other=np.inf)

            # Indices associated to the minimum correct pressure
            min_pres_idx = valid_pres.argmin(dim="N_LEVELS")

            # Extract associated PSAL (good QC and good pressure)
            if i_var == 0:
                psal_results = load_param(Sprof["PSAL"], valid_pres)
            else:
                psal_adj_results = load_param(Sprof["PSAL_ADJUSTED"], valid_pres)

        # Xarray -> Numpy:
        cycle_results: np.ndarray = Sprof["CYCLE_NUMBER"].to_numpy()
        psal_results = psal_results.to_numpy()
        psal_adj_results = psal_adj_results.to_numpy()
        psal_mixt_results = psal_adj_results.copy()
        isbad = np.isnan(psal_mixt_results)
        psal_mixt_results[isbad] = psal_results[isbad]

        ############################################################################################
        # Look for the correct temperature near the surface in the Sprof Data
        #
        # Attention : In Rtraj, all TEMP_QC = 3
        # The Sprof contains TEMP for the profile and the near surface.
        # TEMP_ADJUSTED doesn't contain the near surface data (it's empty)
        # We work on TEMP.

        valid_qc = (
            (Sprof["TEMP_QC"] == 1) | (Sprof["TEMP_QC"] == 2) | (Sprof["TEMP_QC"] == 3)
        )

        # Mask
        valid_mask = valid_qc & valid_pres_range

        # Pressure = Inf if not ok
        valid_pres = Sprof["PRES"].where(valid_mask, other=np.inf)

        # Extract associated PSAl (with QC and pressure).
        temp_results = load_param(Sprof["TEMP"], valid_pres)

        ############################################################################################

        # Read INair and INWater data
        Rtraj_inair = Rtraj.where(
            Rtraj["MEASUREMENT_CODE"].isin(in_air_codes), drop=True
        )
        Rtraj_inwater = Rtraj.where(
            Rtraj["MEASUREMENT_CODE"].isin(in_water_codes), drop=True
        )

        # When CarryOver is used, we need to mix Inair and Inwater data:
        cycles_communs = xr.DataArray(
            np.intersect1d(Rtraj_inair["CYCLE_NUMBER"], Rtraj_inwater["CYCLE_NUMBER"]),
            dims="N_CYCLE",
        )
        Rtraj_inair = Rtraj_inair.where(
            Rtraj_inair["CYCLE_NUMBER"].isin(cycles_communs), drop=True
        )
        Rtraj_inwater = Rtraj_inwater.where(
            Rtraj_inwater["CYCLE_NUMBER"].isin(cycles_communs), drop=True
        )

        # Median per cycle
        Rtraj_inair = Rtraj_inair.groupby("CYCLE_NUMBER").median(skipna=True)
        Rtraj_inwater = Rtraj_inwater.groupby("CYCLE_NUMBER").median(skipna=True)

        # Transform dates from int to datetime:
        Rtraj_inair["JULD"] = (
            "CYCLE_NUMBER",
            pd.to_datetime(Rtraj_inair["JULD_INT"].values),
        )
        Rtraj_inwater["JULD"] = (
            "CYCLE_NUMBER",
            pd.to_datetime(Rtraj_inwater["JULD_INT"].values),
        )

        # We used PSAL/PSAL_ADJUSTED from Sprof.
        # PSAL and TEMP are used to calculate NCEP PPOX.
        for i_data in range(
            Rtraj_inair["PSAL"].size
        ):  # todo: fix syntax, da.size is not robust here
            isok = np.where(
                cycle_results == Rtraj_inair["CYCLE_NUMBER"][i_data].values
            )[0]
            if isok.size > 0:
                if which_psal == 1:
                    if i_data == 0:
                        log.info(f"PSAL Data is used")
                    Rtraj_inair["PSAL"][i_data] = psal_results[isok][0]
                    Rtraj_inwater["PSAL"][i_data] = psal_results[isok][0]
                elif which_psal == 2:
                    if i_data == 0:
                        log.info(f"PSAL_ADJUSTED Data is used")
                    Rtraj_inair["PSAL"][i_data] = psal_adj_results[isok][0]
                    Rtraj_inwater["PSAL"][i_data] = psal_adj_results[isok][0]
                else:
                    if i_data == 0:
                        log.info(f"PSAL_ADJUSTED is used if exists, otherwise PSAL.\n")
                    Rtraj_inair["PSAL"][i_data] = psal_mixt_results[isok][0]
                    Rtraj_inwater["PSAL"][i_data] = psal_mixt_results[isok][0]
            else:
                Rtraj_inair["PSAL"][i_data] = np.nan
                Rtraj_inwater["PSAL"][i_data] = np.nan

            if np.abs(Rtraj_inair["TEMP"][i_data] - temp_results[isok][0]) > 0.5:
                log.warning(
                    f"Cycle {cycle_results[isok][0]}\nRtraj Temperature differs by more than 0.5 degrees from Sprof Temperature"
                )

        # We affect a position to each cycle.
        Rtraj_inair["LONGITUDE_ARGO"] = (
            ("CYCLE_NUMBER"),
            np.nan * np.ones(len(Rtraj_inair.coords["CYCLE_NUMBER"])),
        )
        Rtraj_inair["LATITUDE_ARGO"] = (
            ("CYCLE_NUMBER"),
            np.nan * np.ones(len(Rtraj_inair.coords["CYCLE_NUMBER"])),
        )
        Rtraj_inwater["LONGITUDE_ARGO"] = (
            ("CYCLE_NUMBER"),
            np.nan * np.ones(len(Rtraj_inwater.coords["CYCLE_NUMBER"])),
        )
        Rtraj_inwater["LATITUDE_ARGO"] = (
            ("CYCLE_NUMBER"),
            np.nan * np.ones(len(Rtraj_inwater.coords["CYCLE_NUMBER"])),
        )

        for i, cycle_number in enumerate(Rtraj_inair.coords["CYCLE_NUMBER"].values):
            matching_indices = np.where(
                (Sprof["CYCLE_NUMBER"].values == cycle_number)
                & (Sprof["DIRECTION"] == "A")
            )[0]
            if len(matching_indices) > 0:
                matching_index = matching_indices[0]  # We assume a unique match
                Rtraj_inair["LONGITUDE_ARGO"].values[i] = Sprof["LONGITUDE"].values[
                    matching_index
                ]
                Rtraj_inair["LATITUDE_ARGO"].values[i] = Sprof["LATITUDE"].values[
                    matching_index
                ]
                Rtraj_inwater["LONGITUDE_ARGO"].values[i] = Sprof["LONGITUDE"].values[
                    matching_index
                ]
                Rtraj_inwater["LATITUDE_ARGO"].values[i] = Sprof["LATITUDE"].values[
                    matching_index
                ]

        # We only keep needed variables:
        Rtraj_inair = Rtraj_inair[
            [
                "LONGITUDE_ARGO",
                "LATITUDE_ARGO",
                "PPOX_DOXY",
                "TEMP",
                "PSAL",
                "JULD",
                "CYCLE_NUMBER",
            ]
        ]
        Rtraj_inwater = Rtraj_inwater[
            [
                "LONGITUDE_ARGO",
                "LATITUDE_ARGO",
                "PPOX_DOXY",
                "TEMP",
                "PSAL",
                "JULD",
                "CYCLE_NUMBER",
            ]
        ]

        return Rtraj_inair, Rtraj_inwater


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
