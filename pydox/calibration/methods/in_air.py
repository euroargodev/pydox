from typing import Any, Self, Optional
from collections import OrderedDict
from functools import partial

import numpy as np

from pydox.utils.casting import to_list
from pydox.utils.compute import compute_fits, ComputeMethods
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
                    )
                    configs[icfg] = p
                    icfg += 1
        return configs

    def fit(
        self, argofloat_obj: Optional[Any] = None, method: ComputeMethods = "sequential"
    ) -> Self:
        """Compute calibration coefficients for all possible configuration set and one Argo float

        According to instance configurations (self.configs), this method is in charge of:
        - Loading/preprocessing Argo Float data,
        - Loading/preprocessing Reference data,
        - Executing all possible computations, sequentially or in parallel

        All of these steps are delegated to external functions taking `argofloat_obj` and one value from `self.configs` as input.
        """

        # We first need to load data that will be used to fit:
        # Data should probably be loaded BEFORE fit to be shared with all concurrent computations

        # Load Argo float and atmospheric reference data:
        input_data = {}
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
            input_data["PPOX1"] = argofloat_obj["PPOX1"]
            input_data["PPOX2"] = argofloat_obj["PPOX2"]

            # print(
            #     f"Loaded {self._mparam('data.ncep.name')} data from src={self._mparam('data.ncep.src')}"
            # )
            input_data["NCEP_PPOX"] = np.random.random_sample(
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

        compute_fits([], lambda x: x, method=method)

        # Gather more detailed results in dedicated placeholders of the instance:
        for iset, result in results.items():
            self._coefs[iset]: CoefficientsInAir = result.coefs
            self._fit_data[iset] = result.fit_data

            # Possibly add more data:
            self._fit_data[iset]["cycle_bounds"] = params2cycs(
                self.configs[iset], argofloat_obj
            )

        # Update fitted status:
        self._fitted = True
        self._fitted_float = {
            "WMO": argofloat_obj["WMO"],
            "CYCLE_NUMBER": params2cycs(self.configs[0], argofloat_obj),
            # self.configs[*].cycles are all the same
        }
        return self
