from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, Self, Optional
import json

from collections import OrderedDict
from dataclasses import dataclass, asdict

import pydox as do
from pydox._config.config import check_config, Config
from pydox._config.utils import format_value_txt, dict_to_string
from pydox.calibration.core import Workflow
from pydox.calibration.method import Method, list_methods
from pydox.calibration.commodities import ParamsClimatology, ParamsInAir, Data
from pydox.calibration.methods.in_air import MethodInAir
from pydox.calibration.methods.climatology import MethodClimatology



def Calibration(method: Optional[str] = None, *args, **kwargs)-> MethodInAir | MethodClimatology:
    """Facade to create a single methodology calibration workflow"""
    if method is None:
        method = do.get_params("calibration_methods.default")

    if method not in list_methods():
        raise ValueError("lorem ipsum")

    if method == "in_air":
        return MethodInAir(*args, **kwargs)
    elif method == "climatology":
        return MethodClimatology(*args, **kwargs)
    else:
        raise NotImplementedError


class CalibrationSet(Workflow):
    """
    Facade to handle a collection of methodology implementations

    Support more than one configuration
    Handle sequential or parallel execution of configuration sets
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._methods: OrderedDict[int, Method] = (
            OrderedDict()
        )  # internal placeholder for all methods to be registered ('Method' instances)

    def __repr__(self):
        summary: list[str] = super().__repr__().split("\n")
        summary[0] = "<pydox.Workflow.CalibrationSet>"
        return "\n".join(summary)

    def commit(self, m: MethodInAir | MethodClimatology) -> Self:
        """This method looks like the real added difference compared to a 'Workflow' for a single method ('Method')"""
        ii = len(self._methods)
        self._methods.update({ii: deepcopy(m)})
        return self

    def _flatten_configs(self) -> OrderedDict[int, dataclass]:
        configs, icfg = OrderedDict(), 0
        for im, m in self._methods.items():
            for idc, dc in m.configs.items():
                configs[icfg] = dc
                icfg += 1
        return configs

    def fit(self, data: Any) -> Self: ...

