from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, Self, Optional
import json

from collections import OrderedDict
from dataclasses import dataclass, asdict

import pydox as do
from pydox._config.config import check_config, Config
from pydox._config.utils import format_value_txt, dict_to_string


class Workflow(ABC):
    """
    Base class for a calibrations
    - Support more than one configuration set
    - Support more than one method

    Notes
    -----
    There is some ambiguity here wrt the use of the word "configuration":
    - It may refer to the user-level configuration object that holds all possible library settings and method parameters
    - But it may also refer to the lower-level unique set of parameters describing a unique calibration computation.

    We shall review and fix this.

    Notes
    -----
    A 'Workflow' instance (deep)copies the global configuration object internally and will work only with this copy afterward.

    Therefore, any changes to the global configuration made after the creation of an instance, won't have any impact
    on that 'Workflow' instance.
    """

    def __init__(self, *args, **kwargs):
        config: Config = kwargs.get("config", do.params)

        # Implement some validation on this config argument:
        config = check_config(
            config
        )  # Will raise an error if not a valid configuration
        # but, this may not be coherent with the from_config class method expectation, see below.

        # Init private placeholders
        self._cfg: Config = deepcopy(config)
        self._fitted: bool = False
        self._fitted_float: Dict = None # Used to register float WMO/CYCLES used for fit
        self._coefs = OrderedDict()
        self._fit_data = OrderedDict()

    @classmethod
    def from_config(cls, config, *args, **kwargs) -> "Workflow":
        """

        I'm not sure yet what is the best way to implement this:

        - Should the config argument _overload_ the default configuration (do.params)
        - Or should the config argument be a full configuration, ie _overwrite_ the default configuration (do.params)

        """
        # return cls(config=config, *args, **kwargs)
        raise NotImplementedError

    def _repr_params_shared(self) -> list[str]:
        """Return a description of parameters shared by all methods

        (These are stored into a specific group in the configuration, eg 'calibration_parameters')

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []

        # Piecewise subgroup:
        summary += [f"  piecewise: {json.dumps(self._sparam('piecewise'))}"]

        # Initial conditions subgroup:
        summary += [f"  initial_guess: {json.dumps(self._sparam('initial_guess'))}"]

        # Cycle numbers subgroup:
        summary += [f"  cycles: {json.dumps(self._sparam('cycles'))}"]

        # Fit drift:
        summary += [f"  fit_drift: {json.dumps(self._sparam('fit_drift'))}"]

        return summary

    def _repr_configs(self) -> list[str]:
        """Return a description of all unique computation configurations

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []
        for ii, cfg in self.configs.items():
            d: dict = asdict(
                cfg
            )  # cfg is a commodity dataclass produced by self._flatten_configs
            method = d["method"]
            d.pop("method")
            if not self.get_params("pydox.verbose.configs"):
                d.pop("src")
            summary += [f"  {ii}: method='{method}' {d}"]

        return summary

    def _repr_fitted(self)->list[str]:
        """Return a description of the fit

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []
        if self.fitted:
            summary += [f"fitted: {self.fitted} (WMO={self._fitted_float.get('WMO', '?')}, CYCLES {self._fitted_float.get('CYCLE_NUMBER', '?')})"]
        else:
            summary += [f"fitted: {self.fitted}"]
        return summary

    def __repr__(self):
        """Repr data shared by any class inheriting from this based class"""
        summary = ["<pydox.Workflow>"]

        [summary.append(line) for line in self._repr_fitted()]

        summary += [""]  # Blank line

        summary += ["parameters (shared by all methods):"]
        [summary.append(line) for line in self._repr_params_shared()]

        summary += [""]  # Blank line

        if self.n_configs == 0:
            summary += ["no configurations"]
        else:
            summary += [f"configurations [{self.n_configs}]:"]
            [summary.append(line) for line in self._repr_configs()]

        return "\n".join(summary)

    @property
    def fitted(self) -> bool:
        """Was the instance fitted at least once ?"""
        return self._fitted

    def get_params(self, *args, **kwargs):
        """Get configuration parameter(s) for this instance only"""
        return do.get_params(*args, **kwargs, config=self._cfg)

    def set_params(self, *args, **kwargs) -> Self:
        """Set configuration parameter(s) for this instance only"""
        do.set_params(*args, **kwargs, config=self._cfg)
        return self

    def reset_params(self, *args, **kwargs) -> Self:
        """Reset configuration parameter(s) to instantiation initial value(s)

        ‼️ This method does not reset parameters to current _default_ or _factory_ values, but to values at instantiation time.
        """
        do.reset_params(*args, **kwargs, config=self._cfg)
        return self

    def _sparam(
        self, param: Optional[str] = None, fallback: Optional[Any] = None
    ) -> Any:
        """Return parameters shared by all methods

        Get one shared parameter value, and possibly return a fallback if value is None.
        (These are stored into a specific group in the configuration, eg 'calibration_parameters')

        This is a private method to shorten syntax when retrieving parameters
        """
        if param is not None:
            value: Any | Dict[str, Any] = self.get_params(
                f"calibration_parameters.{param}"
            )
        else:
            value: Dict[str, Any] = self.get_params("calibration_parameters")
        return value if value is not None else fallback

    @abstractmethod
    def _flatten_configs(self) -> OrderedDict[int, dataclass]:
        """Scan all parameters and create an ordered dictionary with all configurations to compute

        Dictionary keys are integers, values are commodity dataclasses with all required parameters for the coefs computation.

        Notes
        -----
        This is a private method that "translates" information from the user-level API configuration
        into internal dataclasses (see commodities) to be consumed by low-level computational functions.
        """
        raise NotImplementedError

    def flatten_configs(self) -> OrderedDict[int, dataclass]:
        """Return a dictionary with all possible configurations

        Dictionary keys are integers, values are commodity dataclasses with all required parameters for the coefs computation.

        Notes
        -----
        This is a method that "translates" information from the user-level API configuration
        into commodity dataclasses to be consumed by low-level computational functions.
        """
        return self._flatten_configs()

    @property
    def configs(self) -> OrderedDict[int, dataclass]:
        """A property to directly access the dictionary of configurations"""
        return self.flatten_configs()

    @property
    def n_configs(self) -> int:
        """Return the number of all possible configurations"""
        return len(self.flatten_configs())

    @abstractmethod
    def fit(self, data: Any) -> Self:
        raise NotImplementedError

    @property
    def coefs(self) -> OrderedDict[int, dataclass]:
        """A property to directly access the dictionary of coefficients"""
        if self.fitted:
            return self._coefs
        else:
            raise ValueError(f"No coefficients computed")