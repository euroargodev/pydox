from typing import Any, Self, Optional, Callable, Iterable, Annotated, TypedDict
from collections import OrderedDict
from functools import partial
import logging
from copy import deepcopy

import numpy as np
import argopy as ar
import xarray as xr
import matplotlib.pyplot as plt

import pydox as do
from pydox._config.config import Config
from pydox.utils.casting import to_list, is_ctelist
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
from pydox.calibration.methods.utils import (
    get_data_for_one_parameterset_for_in_air_method,
)


log = logging.getLogger("pydox.calibration.methods.in_air")

#
# class ArgoData:
#
#     def __init__(self, wmo: int, **kwargs) -> None:
#         self._cfg: Config = deepcopy(kwargs.get("config", do.params))
#         self.a_float: ar.ArgoFloat = ar.ArgoFloat(
#             wmo, host=do.get_params("argo.src", config=self._cfg), cache=True
#         )
#         self.cast = kwargs.get("cast", True)
#         self._sprof = None
#         self._rtraj = None
#
#     @property
#     def Sprof(self) -> xr.Dataset:
#         if self._sprof is None:
#             self._sprof = self.a_float.open_dataset("Sprof", cast=self.cast)
#         return self._sprof
#
#     @property
#     def Rtraj(self) -> xr.Dataset:
#         if self._rtraj is None:
#             self._rtraj = self.a_float.open_dataset("Rtraj", cast=self.cast)
#         return self._rtraj


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
                        initial_gain=Data(self._sparam("initial_guess.gain"), 1.0),
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

    def fit(
        self,
        a_float: ar.ArgoFloat,
        method: ExecutionMethods = "thread",
        debug_plot: bool = False,
    ) -> Self:
        """Compute calibration coefficients for all possible configuration set and one Argo float

        According to this instance configurations (self.configs), this method is in charge of:
        - Loading/preprocessing Argo Float data,
        - Loading/preprocessing Reference data (eg: from NCEP),
        - Executing all possible computations, sequentially or in parallel

        All of these steps are delegated to external functions taking `argofloat_obj` and a :class:`ParameterSet` (ie one value from `self.configs`) as input.

        Parameters
        ----------
        a_float
            An object that will be able to return Argo float data
            #Todo: define clearly what we expect here

        method: ExecutionMethods

        Returns
        -------
        Self

        Comments
        --------
        In order to load data that will be used by each fit, we need settings from the list of configurations:
        But the list of configurations (self.configs) is a list of ParameterSet that does not contain ALL
        possibly required settings from the configuration (eg: argo QC

        """

        ############### Load data
        # We first need to load data that will be used to fit for each configuration
        input_data: dict[int, Any] = {}

        # todo Collect input data in parallel ?
        for iset, params in self.configs.items():
            iset, data = get_data_for_one_parameterset_for_in_air_method(
                a_float, self._cfg, params, iset, debug_plot=debug_plot
            )
            input_data[iset] = data

        ############### Execute all computations
        # argument 'method' determines how to do it:
        # - 'sequential': one after the other
        # - 'thread'/'process' or a Dask client: in parallel

        # When we had one possible input_data:
        # fct = partial(inair_fit, data=input_data)
        # items = [(iset, params) for iset, params in self.configs.items()]
        # results: FitResults = compute_fits(items, fct, method=method)

        # Now we have as many input_data as unique configuration:
        items = [
            (iset, params, input_data[iset]) for iset, params in self.configs.items()
        ]
        results: FitResults = compute_fits(items, inair_fit, method=method)

        ############### Finalize
        # Gather more detailed results in dedicated placeholders of the instance:
        for iset, result in results.items():
            self._coefs[iset]: CoefficientsInAir = result.coefs
            self._fit_data[iset] = result.fit_data

            # Possibly add more data:
            # (be careful not to overwrite an attribute already set by inair_fit)
            self._fit_data[iset]["cycle_bounds"] = self.configs[iset].cycles

        # Update fitted status:
        self._fitted = True
        self._fitted_float = {
            "WMO": a_float.WMO,
        }
        return self
