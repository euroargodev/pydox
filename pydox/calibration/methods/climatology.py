from typing import Any, Self
from collections import OrderedDict

from pydox.utils.casting import to_list
from pydox._config.utils import format_value_txt
from pydox.commodities import ConfigsDict, ParameterSet, ParamsClimatology, Data
from pydox.calibration.method import Method


class MethodClimatology(Method):
    """Quick and dirty implementation for dev purposes"""

    rcgroup = "climatology"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if we have everything we need in the configuration to run the method:
        ...

    def _repr_params(self) -> list[str]:
        """Return a description of parameters for the 'climatology' method"""
        summary = []
        for param in ["min_pressure", "max_pressure"]:
            value = self._mparam(param)
            summary += [f"  {param}: {format_value_txt(value)}"]

        [summary.append(line) for line in self._repr_dataset()]

        return summary

    def _flatten_configs(self) -> ConfigsDict:
        """Define the entire configuration space to explore with the 'climatology' method"""
        configs: ConfigsDict = OrderedDict()
        icfg: int = 0
        for fit_drift in to_list(self._sparam("fit_drift")):
            for min_pressure in to_list(self._mparam("min_pressure")):
                for max_pressure in to_list(self._mparam("max_pressure")):
                    for ds in to_list(self._mparam("dataset")):
                        p: ParameterSet = ParamsClimatology(
                            fit_drift=fit_drift,
                            cycles=self._sparam("cycles"),
                            initial_gain=Data(self._sparam("initial_guess.gain"), 1.0),
                            initial_drift=Data(
                                self._sparam("initial_guess.drift"), 0.0
                            ),
                            min_pressure=min_pressure,
                            max_pressure=max_pressure,
                            dataset=ds,
                            src=self._mparam(f"data.{ds}.src"),
                            dummy=icfg
                            + 1000,  # For dev. to track config number down to coefs results
                        )
                        configs[icfg] = p
                        icfg += 1
        return configs

    def fit(self, data: Any) -> Self:
        raise NotImplementedError

    def load_input_data(
        self,
        *args,
        **kwargs,
    ):
        raise NotImplementedError
