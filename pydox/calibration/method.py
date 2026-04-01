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
from pydox.calibration.commodities import ParamsClimatology, ParamsInAir, Data, Coefficients


def list_methods() -> list[str]:
    """Return the list of calibration methods"""
    methods = []
    for key in do.get_params("calibration_methods"):
        if key != "default":
            methods.append(key)
    return methods


class Method(Workflow, ABC):
    """
    Base class for one methodology implementation
    Support more than one configuration (but only one method)
    """

    rcgroup: str = None
    """Group name of the configuration file section to get this method parameters"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _mparam(self, param: str, fallback: Optional[Any] = None) -> Any:
        """Return method parameter

        Get one specific method parameter value, and possibly return a fallback if value is None.
        (These parameters are stored into a specific group in the configuration, eg 'calibration_methods.in_air')
        """
        value = self.get_params(f"calibration_methods.{self.rcgroup}.{param}")
        return value if value is not None else fallback

    @property
    def method(self) -> str:
        """A more verbose description of this method

        Allow to print more information about the method than the configuration group name, eg some long_name
        Can be used in the repr of the class, or figure titles for instance
        """
        try:
            y = self._mparam("long_name", None)  # long_name is not necessarily defined
            y = y if y is not None else self.rcgroup
        except:
            y = self.rcgroup
        return y

    @abstractmethod
    def _repr_params(self) -> list[str]:
        """Return a description of parameters specific to a method

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        raise NotImplementedError

    def _repr_dataset(self) -> list[str]:
        """Return a description of dataset parameters

        This method is in the `Method` base class because we assume that the
        'dataset' and 'data' subgroups in the configuration is organised
        similarly for all methods group, typically:
        ```yaml
          dataset: 'some_ds'
          data:
            some_ds:
              name: 'hello world'
              src: null
            another_ds:
              name: 'bye bye'
              src: null
        ```

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []
        dataset_names = to_list(self._mparam("dataset"))
        if len(dataset_names) == 1:
            ds = dataset_names[0]
            summary += [f"  dataset: '{ds}'"]
            lines = dict_to_string(self._mparam(f"data.{ds}")).split("\n")
            summary += [f"    {line}" for line in lines]
        else:
            summary += [f"  dataset: {dataset_names}"]
            for ds in dataset_names:
                summary += [f"    data: '{ds}'"]
                lines = dict_to_string(self._mparam(f"data.{ds}")).split("\n")
                summary += [f"      {line}" for line in lines]
        return summary

    def __repr__(self):
        """Overwrite the basic Workflow repr"""
        # summary : list[str] = super().__repr__().split("\n")

        if self.method == self.rcgroup:
            summary = [f"<pydox.Workflow.Calibration.{self.rcgroup}>"]
        else:
            summary = [
                f"<pydox.Workflow.Calibration.{self.rcgroup}> '{self.method.title()}'"
            ]

        summary += [f"fitted: {self.fitted}"]

        summary += ["parameters (shared by all methods):"]
        [summary.append(line) for line in self._repr_params_shared()]

        summary += [f"parameters (specific to '{self.rcgroup}'):"]
        [summary.append(line) for line in self._repr_params()]

        summary += [f"configurations [{self.n_configs}]:"]
        [summary.append(line) for line in self._repr_configs()]

        return "\n".join(summary)

