from copy import deepcopy
from typing import Self, Optional
from collections import OrderedDict

import numpy as np
import pydox as do
from pydox._config.utils import list_methods
from pydox.calibration.methods.in_air import plots as in_air_plots
from pydox.commodities import ConfigsDict, PlotParams
from pydox.calibration.spec import Workflow
from pydox.calibration.method import Method
from pydox.calibration.methods.in_air.spec import MethodInAir
from pydox.calibration.methods.climatology import MethodClimatology


def Calibration(
    method: Optional[str] = None, *args, **kwargs
) -> MethodInAir | MethodClimatology:
    """Create a single methodology calibration

    Parameters
    ----------
    method: Optional[str]

        Name of the method implementation to create.

        By default, creates a method defined with the ``calibration_methods.default`` setting.

    Returns
    -------
    :class:`pydox.calibration.MethodInAir`, :class:`pydox.calibration.MethodClimatology`

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
    """Collection of methodology implementations

    Notes
    -----
    - Support more than one calibration method
    - Handle sequential or parallel execution of configuration sets

    Examples
    --------
    .. code-block:: python

        from pydox import Calibration, CalibrationSet

        s = CalibrationSet()
        s.commit(Calibration('in_air').set_params('calibration_methods.in_air', carryover=[False, True], dataset=['ncep', 'era5']))
        s.commit(Calibration('climatology').set_params('calibration_methods.climatology.max_pressure', [25., 50.]))

        s.n_configs
        s.configs

        s.fit(a_float)

        s.fitted
        s.coefs
        s.set_best_fit
        s.best_fit

        s.plot
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._methods: OrderedDict[int, Method] = (
            OrderedDict()
        )  # internal placeholder for all methods to be registered (which are 'Method' children instances)

    def __repr__(self):
        summary: list[str] = super().__repr__().split("\n")
        summary[0] = f"<pydox.Workflow.CalibrationSet> {self.name}"
        return "\n".join(summary)

    def commit(self, o: MethodInAir | MethodClimatology) -> Self:
        """This method looks like the real added difference compared to a 'Workflow' for a single method ('Method')"""
        ii = len(self._methods)
        self._methods.update({ii: deepcopy(o)})
        return self

    def uid(self, icfg: int = None) -> str:
        """UID for this CalibrationSet or a specific configuration"""
        if icfg is None:
            return self._uid()
        else:
            this_icfg: int = 0
            for im, m in self._methods.items():
                for idc, dc in m.configs.items():
                    if this_icfg == icfg:
                        return m.uid(idc)
                    this_icfg += 1
        raise ValueError(f"Invalid configuration id {icfg}")

    def _flatten_configs(self) -> ConfigsDict:
        # This method implementation *imposes* how to 'iterate' over methods and their ordered placeholders (eg: coefs, fit_data, ...).
        # To keep any CalibrationSet ordered placeholder consistent, we need to iterate: 1st on method, then on configurations.
        configs: ConfigsDict = OrderedDict()
        icfg: int = 0
        for im, m in self._methods.items():
            for idc, dc in m.configs.items():
                configs[icfg] = dc
                icfg += 1
        return configs

    def is_cumulative(self) -> bool:
        """Check if this instance can perform a cumulative fit

        An instance is eligible if:
        - There is at least 2 methods
        - There is only one configuration for each method
        """
        if self.n_configs < 2:
            raise ValueError(
                f"Fit with cumulative gain requires at least 2 configurations"
            )

        for im, this_method in self._methods.items():
            if this_method.n_configs != 1:
                raise ValueError(
                    "Fit with cumulative gain requires a single configuration for each methods"
                )

        # Return False if methods are not different ?
        # if len(np.unique([m.rcgroup for m in self._methods.values()])) == 1:
        #     return False

        return True

    def load_input_data(
        self,
        argofloat_obj,
        *args,
        **kwargs,
    ) -> Self:
        icfg: int = 0
        for im, this_method in self._methods.items():
            this_method.load_input_data(argofloat_obj, *args, **kwargs)
            for idc, dc in this_method.configs.items():
                self._input_data[icfg] = this_method.input_data[idc]
                icfg += 1

    def fit(
        self,
        argofloat_obj,
        cumulative: Optional[bool] = False,
        **kwargs,
    ) -> Self:
        self._fitted_float["WMO"] = argofloat_obj.WMO

        if not cumulative:
            icfg: int = 0
            for im, this_method in self._methods.items():
                this_method.fit(argofloat_obj, **kwargs)

                # Gather detailed results:
                for idc, dc in this_method.configs.items():
                    self._input_data[icfg] = this_method.input_data[idc]
                    self._coefs[icfg] = this_method.coefs[idc]
                    self._fit_data[icfg] = this_method._fit_data[idc]
                    self._fitted_float["CYCLE_NUMBER"][icfg] = (
                        this_method._fitted_float["CYCLE_NUMBER"][idc]
                    )
                    icfg += 1

        elif (
            self.is_cumulative()
        ):  # (cumulative was set to True, so we check eligibility immediately)

            icfg: int = 0
            for im, this_method in self._methods.items():
                this_method.fit(argofloat_obj, **kwargs)
                idc = 0  # We can safely use the 1st value because all methods have a single configuration (see self.is_cumulative()).

                # Gather more detailed results in dedicated placeholders of the instance:
                self._input_data[icfg] = this_method.input_data[idc]
                self._coefs[icfg] = this_method.coefs[idc]
                self._fit_data[icfg] = this_method.fit_data[idc]
                self._fitted_float["CYCLE_NUMBER"][icfg] = this_method._fitted_float[
                    "CYCLE_NUMBER"
                ][idc]

                # Update next method configuration initial conditions with this estimate:
                if im + 1 < len(self._methods):
                    coefs = this_method.coefs[idc]
                    self._methods[im + 1].set_params(
                        "calibration_parameters.initial_guess.gain",
                        coefs.gain.value,
                    )
                    # So it is the fit method responsibility to use the initial value accordingly

                icfg += 1

        # Update fitted status:
        self._fitted = all(
            [m.fitted for m in self._methods.values()]
        )  # is the set fitted when all methods are fitted, or at least one ?

        ############### Plot
        # Create a parameter obj for plots
        ppar = PlotParams(
            watermark=self.name,
            dpi=self.get_params("plots.dpi"),
            level=self.get_params("plots.level"),
            uid=self.uid(),
        )
        if np.all(np.unique([m.rcgroup for m in self._methods.values()]) == "in_air"):
            # If all methods are in-air, we can safely generate these plots:

            if "hue" in self.get_params("plots.configs_layout"):
                in_air_plots.plot_fit_results_hue(
                    self.input_data, self.coefs, ppar=ppar
                )

            if "subplot" in self.get_params("plots.configs_layout"):
                in_air_plots.plot_fit_results_subplot(
                    self.input_data, self.coefs, ppar=ppar
                )

            if "figure" in self.get_params("plots.configs_layout"):
                in_air_plots.plot_fit_results_figure(
                    self.input_data, self.coefs, ppar=ppar
                )

        return self
