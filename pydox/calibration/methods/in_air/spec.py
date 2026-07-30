from typing import Any, Self, Optional
from collections import OrderedDict
from functools import partial

import argopy as ar

from pydox._config.utils import format_value_txt
from pydox.reporting.logs import getLogger
from pydox.utils.casting import to_list
from pydox.utils.compute import compute_fits, ExecutionMethods
from pydox.commodities import (
    Data,
    ConfigsDict,
    ParameterSet,
    ParamsInAir,
    CoefficientsInAir,
    FitResults,
    PlotParams,
    TPlotParams,
)
from pydox.core import in_air
from pydox.calibration.method import Method
from pydox.calibration.methods.in_air.utils import (
    get_data_for_one_parameterset_for_in_air_method,
)
from pydox.calibration.methods.in_air.plots import (
    plot_fit_results_hue,
    plot_fit_results_subplot,
)

log = getLogger("pydox.calibration.methods.in_air.spec", context_level=20)


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

    def load_input_data(
        self,
        a_float: ar.ArgoFloat,
        ppar: Optional[TPlotParams] = None,
        **kwargs,
    ) -> Self:
        """Load input data for the flatten list of configurations

        This method populates self._input_data
        """
        refresh: bool = kwargs.get("refresh", False)

        # Create a parameter generator for plots, to be communicated downstream at lower levels:
        if ppar is None:
            ppar = partial(
                PlotParams,
                watermark=self.name,
                dpi=self.get_params("plots.dpi"),
                level=self.get_params("plots.level"),
            )

        # We first need to load data that will be used for fit for each configuration
        input_data_for_fit: dict[int, Any] = {}

        # todo Collect input data in parallel ?
        for iset, params in self.configs.items():
            if refresh or iset not in self._input_data:
                log.info(f"Load input data for config #{iset} ...")
                this_ppar = partial(
                    ppar,
                    watermark=f"{self.name}\nConfig #{iset}",
                    uid=self.uid(iset),
                )
                # Call the appropriate lower-level method to load one set of data for a given configuration.
                # The `ppar` function is propagated downstream with updated and appropriate configuration ID.
                # The `uid` argument is also updated to match this specification configuration ID.
                data = get_data_for_one_parameterset_for_in_air_method(
                    a_float,
                    self._cfg,
                    params,
                    uid=self.uid(iset),
                    ppar=this_ppar,
                )
                self._input_data[iset] = data
            else:
                log.info(f"Input data for config #{iset} already in memory")

        return self

    def fit(
        self,
        a_float: ar.ArgoFloat,
        method: ExecutionMethods = "thread",
    ) -> Self:
        """Compute calibration coefficients for all possible configuration set and one Argo float

        According to this instance configurations (self.configs), this method is in charge of:
        - Loading/preprocessing Argo Float data,
        - Loading/preprocessing Reference data (eg: from NCEP),
        - Executing all possible computations, sequentially or in parallel
        - Fill in internal placeholder for coeffcients and fit data

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
        # Create a parameter generator for plots, to be communicated downstream at lower levels:
        ppar = partial(
            PlotParams,
            watermark=self.name,
            dpi=self.get_params("plots.dpi"),
            level=self.get_params("plots.level"),
        )

        ############### Load input data
        # We first need to load data that will be used in fit
        log.info("Start loading input data")
        self.load_input_data(a_float, ppar)
        log.info("End loading input data")

        # Read and store the list of cycle numbers for each configuration
        input_cycs_for_fit = {}
        [
            input_cycs_for_fit.update({iset: data["CYCLE_NUMBER"]})
            for iset, data in self.input_data.items()
        ]

        ############### Execute all computations
        # argument 'method' determines how to do it:
        # - 'sequential': one after the other
        # - 'thread'/'process' or a Dask client: in parallel

        # When we had one possible input_data:
        # fct = partial(inair_fit, data=input_data)
        # items = [(iset, params) for iset, params in self.configs.items()]
        # results: FitResults = compute_fits(items, fct, method=method)

        # Now we have as many input_data as unique configuration:
        log.info("Compute coefficients")
        items = [
            (iset, params, self.input_data[iset])
            for iset, params in self.configs.items()
        ]
        results: FitResults = compute_fits(items, in_air.fit, method=method)

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
        self._fitted_float["WMO"] = a_float.WMO
        self._fitted_float["CYCLE_NUMBER"] = input_cycs_for_fit

        ############### Plot
        # Create a set of plotting parameters to be used under the scope of this .fit method:
        this_ppar: PlotParams = PlotParams.get(ppar)
        this_ppar.uid = self.uid()

        if "hue" in self.get_params("plots.configs_layout"):
            plot_fit_results_hue(self.input_data, self.coefs, ppar=this_ppar)

        if "subplot" in self.get_params("plots.configs_layout"):
            plot_fit_results_subplot(self.input_data, self.coefs, ppar=this_ppar)

        return self
