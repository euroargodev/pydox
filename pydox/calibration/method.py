from abc import ABC, abstractmethod
from typing import Any, Optional
import argopy as ar

import pydox as do
from pydox._config.utils import dict_to_string
from pydox.errors import UnsupportedSetting, UnFitted, UnSelected
from pydox.utils.casting import to_list
from pydox.calibration.spec import Workflow
from pydox.reporting.html import CalibrationHTMLReport


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

    def to_report(
        self, a_float: ar.ArgoFloat, file_name: Optional[str] = None, **kwargs
    ):
        """Create calibration report"""
        if do.get_params("reports.save.format", config=self._cfg) != "html":
            raise UnsupportedSetting(
                f"Only 'html' report format is supported at this time, '{do.get_params('reports.save.format', config=self._cfg)}'."
            )

        if not self.fitted:
            raise UnFitted("Cannot create a report without a fit, use 'fit()'")
        elif self.best_fit is None:
            raise UnSelected(
                "Cannot create a report without a best fit, use 'set_best_fit()'"
            )
        elif self._fitted_float["WMO"] != a_float.WMO:
            raise ValueError(
                f"Reporting must be done with the same float as the fit ! {a_float.WMO} vs {self._fitted_float['WMO']}"
            )

        self._reporter = CalibrationHTMLReport(self, a_float)
        return self._reporter.publish(file_name=file_name, **kwargs)
