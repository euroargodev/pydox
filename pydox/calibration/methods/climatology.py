from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, Self, Optional, LiteralString
import json

from collections import OrderedDict
from dataclasses import dataclass, asdict

import pydox as do
from pydox._config.config import check_config, Config
from pydox._config.utils import format_value_txt, dict_to_string
from pydox.calibration.core import Workflow
from pydox.calibration.utils import to_list
from pydox.calibration.commodities import ConfigsDict, ParamsClimatology, Data, Coefficients, FitResults
from pydox.calibration.method import Method


class MethodClimatology(Method):
    rcgroup = "climatology"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if we have everything we need in the configuration to run the method:
        # [...]

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
        configs : ConfigsDict = OrderedDict()
        icfg : int = 0
        for fit_drift in to_list(self._sparam("fit_drift")):
            for min_pressure in to_list(self._mparam("min_pressure")):
                for max_pressure in to_list(self._mparam("max_pressure")):
                    for ds in to_list(self._mparam("dataset")):
                        p = ParamsClimatology(
                            fit_drift=fit_drift,
                            initial_gain=Data(self._sparam("initial_guess.gain"), 0.0),
                            initial_drift=Data(
                                self._sparam("initial_guess.drift"), 0.0
                            ),
                            min_pressure=min_pressure,
                            max_pressure=max_pressure,
                            dataset=ds,
                            src=self._mparam(f"data.{ds}.src"),
                        )
                        configs[icfg] = p  # let's keep the dataclass
                        icfg += 1
        return configs

    def fit(self, data: Any) -> Self: ...

