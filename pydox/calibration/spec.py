from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, Self, Optional, List
import json

import hashlib
from collections import OrderedDict
from dataclasses import asdict

import numpy as np
import matplotlib as mpl
import argopy as ar
import pydox as do
from pydox._config.config import check_config, Config
from pydox.commodities import (
    ConfigsDict,
    CoefsDict,
    PydoxFigure,
    VALID_FIGURE_CATEGORIES,
)
from pydox.utils.casting import is_ctelist, to_list
from pydox.reporting.utils import configs_figure_list, method_figure_list


class Workflow(ABC):
    """
    Base class for one or more calibrations
    - Support more than one configuration set
    - Support more than one method
    - Support ordered vs sequential vs parallel gain computation

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
        self.name: str = kwargs.get("name", "")

        # Implement some validation on this config argument:
        config = check_config(
            config
        )  # Will raise an error if not a valid configuration
        # but, this may not be coherent with the from_config class method expectation, see below.

        # Init private placeholders:
        self._cfg: Config = deepcopy(
            config
        )  # Used by self.get_params(), self.set_params(), self.reset_params()
        self._input_data = (
            OrderedDict()
        )  # Filled by self.fit() or self.load_input_data(), return by self.input_data
        self._fitted: bool = False  # Filled by self.fit(), return by self.fitted
        self._fitted_float: dict = {
            "WMO": None,
            "CYCLE_NUMBER": {},
        }  # Used to register float WMO/CYCLE_NUMBER used for fit
        self._coefs: CoefsDict = (
            OrderedDict()
        )  # Filled by self.fit(), return by self.coefs
        self._fit_data = OrderedDict()  # Filled by self.fit(), return by self.fit_data

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
        summary += [f"  piecewise (not used): {json.dumps(self._sparam('piecewise'))}"]

        # Initial condition subgroup:
        summary += [f"  initial_guess: {json.dumps(self._sparam('initial_guess'))}"]

        # Cycle numbers subgroup:
        if is_ctelist([c.cycles for c in self.configs.values()]):
            summary += [f"  cycles: {json.dumps(self._sparam('cycles'))}"]
        else:
            summary += [f"  cycles: <Values depend on configurations, see below>"]

        # Fit drift:
        if is_ctelist([c.fit_drift for c in self.configs.values()]):
            summary += [f"  fit_drift: {json.dumps(self._sparam('fit_drift'))}"]
        else:
            summary += [f"  fit_drift: <Values depend on configurations, see below>"]

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
            )  # cfg is a commodity ParameterSet produced by self._flatten_configs
            method = d["method"]
            d.pop("method")
            if not self.get_params("pydox.verbose.configs"):
                d.pop("src")
            summary += [f"  {ii}: method='{method}' {d}"]

        return summary

    def _repr_fitted(self) -> list[str]:
        """Return a description of the fit

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []
        if self.fitted:
            # summary += [
            #     f"fitted: {self.fitted} (WMO={self._fitted_float.get('WMO', '?')}"
            # ]

            cycs_per_config = [c for c in self._fitted_float["CYCLE_NUMBER"].values()]
            if is_ctelist(cycs_per_config):
                summary += [
                    f"fitted: {self.fitted} (WMO={self._fitted_float.get('WMO', '?')}, CYCLES {cycs_per_config[0]})"
                ]
            else:
                summary += [
                    f"fitted: {self.fitted} (WMO={self._fitted_float.get('WMO', '?')}, CYCLES range depend on configurations, see below)"
                ]

        else:
            summary += [f"fitted: {self.fitted}"]
        return summary

    def _repr_coefs(self) -> list[str]:
        """Return a description of coefficients when fitted

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        summary = []
        for ic, coef in self.coefs.items():
            summary += [f"  {ic}: {str(coef)}"]
        return summary

    def __repr__(self):
        """Repr data shared by any class inheriting from this based class"""
        summary = [f"<pydox.Workflow> {self.name}"]

        [summary.append(line) for line in self._repr_fitted()]

        summary += [""]  # Blank line

        summary += ["default parameters shared by all methods:"]
        [summary.append(line) for line in self._repr_params_shared()]

        summary += [""]  # Blank line

        if self.n_configs == 0:
            summary += ["no configurations"]
        else:
            summary += [f"configurations [{self.n_configs}]:"]
            [summary.append(line) for line in self._repr_configs()]

        if self.fitted:
            summary += [""]  # Blank line
            summary += [f"coefficients [{len(self.coefs)}]:"]
            [summary.append(line) for line in self._repr_coefs()]

        return "\n".join(summary)

    def _uid(self, icfg: int = None) -> str:
        """UID for this Workflow or a specific configuration"""
        m = hashlib.sha256()
        m.update(bytes(str(self.name), "utf-8"))
        m.update(bytes(str(self._cfg), "utf-8"))
        configs = (
            self.configs.keys() if icfg is None else ar.utils.checkers.to_list(icfg)
        )
        for c in configs:
            m.update(bytes(str(self.configs[c]), "utf-8"))
        return m.hexdigest()

    def uid(self, icfg: int = None) -> str:
        """UID for this Workflow or a specific configuration"""
        return self._uid(icfg)

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

    def flatten_configs(self) -> ConfigsDict:
        """Return a dictionary with all possible configurations

        Dictionary keys are integers, values are commodity dataclasses with all required parameters for the coefs computation.

        Notes
        -----
        This is a method that "translates" information from the user-level API configuration
        into commodity dataclasses to be consumed by low-level computational functions.
        """
        return self._flatten_configs()

    @property
    def configs(self) -> ConfigsDict:
        """A property to directly access the dictionary of configurations"""
        return self.flatten_configs()

    @property
    def n_configs(self) -> int:
        """Return the number of all possible configurations

        In theory there is always at least 1 configuration.

        But the number of configs depends on:
            `self.configs < self.flatten_configs() < self._flatten_configs()`
        So, if `self._flatten_configs()` is not or partially implemented, `n_configs` can be 0.
        """
        return len(self.flatten_configs())

    @property
    def input_data(self) -> Dict[int, Any]:
        """Input data for fit"""
        return self._input_data

    @abstractmethod
    def load_input_data(self, data: Any) -> Dict[int, Any]:
        """Input data for fit"""
        raise NotImplementedError

    @property
    def coefs(self) -> CoefsDict:
        """A property to directly access the dictionary of coefficients"""
        if self.fitted:
            return self._coefs
        else:
            raise ValueError(f"No coefficients computed")

    @property
    def fit_data(self) -> Dict[int, Any]:
        """Input data for fit"""
        if self.fitted:
            return self._fit_data
        else:
            raise ValueError(f"No coefficients data computed")

    @property
    def configs_figures(self) -> OrderedDict[int, List[PydoxFigure]]:
        """Return figures with similar uid as a configuration

        See Also
        --------
        :class:`Workflow.figures`
        """
        return configs_figure_list(self)

    @property
    def figures(self) -> List[PydoxFigure]:
        """Return figures with similar uid as this workflow instance

        See Also
        --------
        :class:`Workflow.configs_figures`
        """
        return method_figure_list(self)

    @abstractmethod
    def _flatten_configs(self) -> ConfigsDict:
        """Scan all parameters and create an ordered dictionary with all configurations to compute

        Dictionary keys are integers, values are commodity dataclasses with all required parameters for the coefs computation.

        Notes
        -----
        This is a private method that "translates" information from the user-level API configuration
        into internal dataclasses (see commodities) to be consumed by low-level computational functions.
        """
        raise NotImplementedError

    @abstractmethod
    def fit(self, data: Any) -> Self:
        raise NotImplementedError

    def plot(
        self,
        icfg: Optional[int] = None,
        categories: str | list[str] = "fit_results",
        configs_layout: str | list[str] = ["hue"],
    ) -> list[mpl.figure.Figure]:
        """Show figures

        Parameters
        ----------
        icfg: int, optional, default = None
           Select plots for a specific configuration number.
           If set to None (default), show only plots shared by all configurations (eg: fit results).
        categories: str | list[str], default = "fit_results"
            Select one or a list of plot categories to show (eg: "debug", "input_data", "fit_results").
            Valid values are in :class:`pydox.commodities.VALID_FIGURE_CATEGORIES`.
        configs_layout: str | list[str], default = "hue"
            Select One or more possible layout for plots with more than one configuration.

        Returns
        -------
        list[mpl.figure.Figure]
        """
        ###### Validate arguments
        cfg_list: list[int] = []
        if icfg is not None:
            cfg_list: list[int] = to_list(icfg)
        for i in cfg_list:
            if i not in np.arange(self.n_configs):
                raise ValueError(
                    f"Invalid configuration number {i}. Valid values are {np.arange(self.n_configs)}"
                )

        categories: list[str] = to_list(
            "fit_results" if categories is None else categories
        )

        if "all" in categories:
            # Select what to display among commodities.VALID_FIGURE_CATEGORIES values:
            categories: list[str] = VALID_FIGURE_CATEGORIES
            # categories: list[str] = ["input_data", "fit_results"]

        for cat in categories:
            if cat not in VALID_FIGURE_CATEGORIES:
                raise ValueError(
                    f"Invalid plot category '{cat}'. Valid values are: {VALID_FIGURE_CATEGORIES}"
                )

        configs_layout: list[str] = to_list(configs_layout)

        ###### Get the list of figures matching arguments
        pfig_list: List[PydoxFigure] = []
        if len(cfg_list) == 0:
            for category in categories:
                for fig in self.figures:
                    if fig.category == category:
                        if "configs_layout" in fig.name:
                            for layout in configs_layout:
                                if f"[configs_layout='{layout}']" in fig.name:
                                    pfig_list.append(fig)
                        else:
                            pfig_list.append(fig)

            emsg = f"No figures correspond to your criteria ! May be you need to specify a specific configuration number in {np.arange(self.n_configs)}"

        else:
            for icfg in cfg_list:
                for category in categories:
                    for fig in self.configs_figures[icfg]:
                        if fig.category == category:
                            pfig_list.append(fig)
            emsg = f"No figures correspond to your criteria ! May be you should not specify a specific configuration number."

        if len(pfig_list) == 0:
            raise ValueError(emsg)

        ###### Show figures
        for fig in pfig_list:
            fig.reload().show()

        return [f.fig for f in pfig_list]
