from copy import deepcopy
from typing import Any, Self, Optional
from collections import OrderedDict

import pydox as do
from pydox._config.utils import list_methods
from pydox.utils.compute import ComputeMethods
from pydox.commodities import ConfigsDict
from pydox.calibration.utils import params2cycs
from pydox.calibration.spec import Workflow
from pydox.calibration.method import Method
from pydox.calibration.methods.in_air import MethodInAir
from pydox.calibration.methods.climatology import MethodClimatology


def Calibration(
    method: Optional[str] = None, *args, **kwargs
) -> MethodInAir | MethodClimatology:
    """Facade to create a single methodology calibration workflow

    Notes
    -----
    With this design, we cannot implement ``Calibration.from_config()``
    """
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
    """Facade to handle a collection of methodology implementations

    Notes
    -----
    - Support more than one configuration
    - Handle sequential or parallel execution of configuration sets
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._methods: OrderedDict[int, Method] = (
            OrderedDict()
        )  # internal placeholder for all methods to be registered (which are 'Method' children instances)

    def __repr__(self):
        summary: list[str] = super().__repr__().split("\n")
        summary[0] = "<pydox.Workflow.CalibrationSet>"
        return "\n".join(summary)

    def commit(self, m: MethodInAir | MethodClimatology) -> Self:
        """This method looks like the real added difference compared to a 'Workflow' for a single method ('Method')"""
        ii = len(self._methods)
        self._methods.update({ii: deepcopy(m)})
        return self

    def _flatten_configs(self) -> ConfigsDict:
        configs: ConfigsDict = OrderedDict()
        icfg: int = 0
        for im, m in self._methods.items():
            for idc, dc in m.configs.items():
                configs[icfg] = dc
                icfg += 1
        return configs

    def fit(self, argofloat_obj, method: ComputeMethods = "sequential") -> Self:

        icfg: int = 0
        for im, this_method in self._methods.items():
            this_method.fit(argofloat_obj=argofloat_obj, method=method)

            # Gather more detailed results in dedicated placeholders of the instance:
            for iset, coefs in this_method._coefs.items():
                self._coefs[icfg] = coefs
                self._fit_data[icfg] = this_method._fit_data[iset]
                icfg += 1

        # Update fitted status:
        self._fitted = all(
            [m.fitted for m in self._methods.values()]
        )  # is the set fitted when all methods are fitted, or at least one ?
        self._fitted_float = {
            "WMO": argofloat_obj["WMO"],
            "CYCLE_NUMBER": params2cycs(self.configs[0], argofloat_obj),
            # self.configs[*].cycles are all the same
        }
        return self
