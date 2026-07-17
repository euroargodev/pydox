from abc import ABC, abstractmethod
from typing import Any, Optional, List
from collections import OrderedDict
import hashlib
import argopy as ar
import numpy as np

from pydox.commodities import PydoxFigure
from pydox._config.utils import dict_to_string
from pydox.utils.casting import to_list
from pydox.calibration.spec import Workflow
from pydox.reporting.utils import configs_figure_list, method_figure_list


class Method(Workflow, ABC):
    """Base class for one methodology implementation.

    Support more than one configuration, but only one method.

    In-air, climatology and ctd-based methodology implementations MUST inherit from this class.

    Examples
    --------
    ..code-block::python

        from pydox import Calibration

        c = Calibration('in_air')
        c.set_params('calibration_methods.in_air', carryover=[False, True])

        c = Calibration('climatology')
        c.set_params('calibration_methods.climatology.max_pressure', [25., 50.])

        c.n_configs
        c.configs

        c.fitted
        c.coefs

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

        Allow to print more information about the method than the configuration group name, eg: some long_name
        Can be used in the repr of the class, or figure titles for instance
        """
        try:
            y = self._mparam("long_name", None)  # long_name is not necessarily defined
            y = y if y is not None else self.rcgroup
        except:
            y = self.rcgroup
        return y

    def _repr_dataset(self) -> list[str]:
        """Return a description of dataset parameters

        This method is in the `Method` base class because we assume that the
        'dataset' and 'data' subgroups in the configuration are organized
        similarly for all methods group, typically:
        ```yaml
          dataset: 'some_ds'  # Define the default dataset to use
          data: # A subgroup with the description of all dataset, always with at least a 'name' and a 'src'
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

    @abstractmethod
    def _repr_params(self) -> list[str]:
        """Return a description of parameters specific to a method

        Returns
        -------
        list[str]
            To be used by :class:`Method.__repr__`
        """
        raise NotImplementedError

    def __repr__(self):
        """Overwrite the basic Workflow repr

        Allows to insert the method specific parameters before the configuration list.
        """
        # summary : list[str] = super().__repr__().split("\n")

        summary = [f"<pydox.Workflow.Calibration.{self.rcgroup}> {self.name}"]

        if self.method != self.rcgroup:
            summary.append(f"Method long name: {self.method.title()}")

        [summary.append(line) for line in self._repr_fitted()]

        summary += [""]  # Blank line

        summary += ["default parameters shared by all methods:"]
        [summary.append(line) for line in self._repr_params_shared()]

        summary += [""]  # Blank line

        summary += [f"parameters (specific to '{self.rcgroup}'):"]
        [summary.append(line) for line in self._repr_params()]

        summary += [""]  # Blank line

        summary += [f"configurations [{self.n_configs}]:"]
        [summary.append(line) for line in self._repr_configs()]

        if self.fitted:
            summary += [""]  # Blank line
            summary += [f"coefficients [{len(self.coefs)}]:"]
            [summary.append(line) for line in self._repr_coefs()]

        return "\n".join(summary)

    def uid(self, icfg: int = None) -> str:
        """UID for this object and configuration"""
        m = hashlib.sha256()
        m.update(bytes(str(self._cfg), "utf-8"))
        configs = (
            self.configs.keys() if icfg is None else ar.utils.checkers.to_list(icfg)
        )
        for c in configs:
            m.update(bytes(str(self.configs[c]), "utf-8"))
        return m.hexdigest()

    @property
    def configs_figures(self) -> OrderedDict[int, List[PydoxFigure]]:
        return configs_figure_list(self)

    @property
    def figures(self) -> List[PydoxFigure]:
        return method_figure_list(self)

    def plot(
        self,
        icfg: Optional[int] = None,
        categories: Optional[str | list[str]] = None,
    ) -> None:
        """Show figures

        Parameters
        ----------
        icfg: int, optional, default = None
           Configuration number to select plots for.
           If set to None (default), consider only plots shared by all configurations.
        """
        cfg_list: list[int] = []
        if icfg is not None:
            # np.arange(0, self.n_configs)
            cfg_list: list[int] = to_list(icfg)

        categories: list[str] = "all" if categories is None else to_list(categories)

        if "all" in categories:
            # Select what to display among commodities.VALID_FIGURE_CATEGORIES values:
            categories: list[str] = ["input_data", "fit_results"]

        fig_list: List[PydoxFigure] = []
        if len(cfg_list) == 0:
            for category in categories:
                for fig in self.figures:
                    if fig.category == category:
                        fig_list.append(fig)

        else:
            for icfg in cfg_list:
                for category in categories:
                    for fig in self.configs_figures[icfg]:
                        if fig.category == category:
                            fig_list.append(fig)

        if len(fig_list) == 0:
            raise ValueError("No figures correspond to your criteria ! ")

        for fig in fig_list:
            fig.reload().show()
