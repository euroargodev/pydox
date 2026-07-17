from typing import Any, Self, Callable
from collections import OrderedDict
import logging
from functools import partial

import numpy as np
import argopy as ar
import matplotlib.pyplot as plt

from pydox._config.utils import format_value_txt
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
)
from pydox.reporting.utils import fig_commit
from pydox.core import in_air
from pydox.calibration.method import Method
from pydox.calibration.methods.in_air.utils import (
    get_data_for_one_parameterset_for_in_air_method,
)


log = logging.getLogger("pydox.calibration.methods.in_air")


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

    def _load_input_data(
        self, a_float: ar.ArgoFloat, pplot: Callable, debug_plot: bool = False
    ) -> dict[int, Any]:
        """Load input data for the flatten list of configurations"""

        # We first need to load data that will be used to fit for each configuration
        input_data_for_fit: dict[int, Any] = {}

        # todo Collect input data in parallel ?
        # todo Cache input data for performances ?
        for iset, params in self.configs.items():
            print(f"Load input data for config #{iset}")
            data = get_data_for_one_parameterset_for_in_air_method(
                a_float,
                self._cfg,
                params,
                pplot=partial(
                    pplot, watermark=f"{self.name}\nConfig #{iset}", uid=self.uid(iset)
                ),
                debug_plot=debug_plot,
                uid=self.uid(iset),
            )
            input_data_for_fit[iset] = data

        return input_data_for_fit

    def fit(
        self,
        a_float: ar.ArgoFloat,
        method: ExecutionMethods = "thread",
        debug_plot: bool = True,
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
        pplot = partial(
            PlotParams, watermark=self.name, dpi=self.get_params("plots.dpi")
        )

        ############### Load data
        # We first need to load data that will be used to fit for each configuration
        print("Load input data")
        input_data_for_fit: dict[int, Any] = self._load_input_data(
            a_float, pplot, debug_plot
        )

        # Read and store the list of cycle numbers for each configuration
        input_cycs_for_fit = {}
        [
            input_cycs_for_fit.update({iset: data["CYCLE_NUMBER"]})
            for iset, data in input_data_for_fit.items()
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
        print("Compute coefficients")
        items = [
            (iset, params, input_data_for_fit[iset])
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

        if debug_plot:
            # One subplot for each config result (n_configs rows, 1 column)
            suptitle = "Final results for this calibration"

            cmap = plt.colormaps.get_cmap("jet").resampled(len(input_data_for_fit))
            fig, ax = plt.subplots(
                nrows=len(input_data_for_fit),
                ncols=1,
                figsize=(10, 5),
                dpi=self.get_params("plots.dpi"),
                sharex=True,
            )
            ax = (
                ax.flatten() if isinstance(ax, np.ndarray) else np.array(ax)[np.newaxis]
            )

            for iset in range(len(input_data_for_fit)):
                xdata = input_data_for_fit[iset]["CYCLE_NUMBER"]
                ydata = input_data_for_fit[iset]["PPOX1"] * self.coefs[iset].gain.value
                if self.coefs[iset].drift is not None:
                    ydata = ydata * (
                        1
                        + self.coefs[iset].drift.value
                        / 100
                        * input_data_for_fit[iset]["Delta_T_REF"]
                        / 365
                    )

                ax[iset].plot(
                    xdata, input_data_for_fit[iset]["REF_PPOX"], ".-k", label="Ref"
                )
                ax[iset].plot(
                    xdata,
                    input_data_for_fit[iset]["PPOX1"],
                    ".-b",
                    label="Non-adjusted (in-air)",
                )
                ax[iset].plot(
                    xdata,
                    ydata,
                    ".-",
                    color=cmap(iset),
                    label=f"Adjusted (config {iset})",
                )

                ax[iset].grid()
                ax[iset].set_xlabel("Float Cycle number of the measurement")
                ax[iset].set_ylabel("Partial pressure of oxygen [mb]")
                ax[iset].legend()
                ax[iset].set_title(f"Correction : {iset}")

            # plt.tight_layout()
            plt.suptitle(suptitle)

            fig_commit(
                fig,
                name=suptitle,
                category="fit_results",
                watermark=self.name,
                config_uid=self.uid(),
            )

        return self
