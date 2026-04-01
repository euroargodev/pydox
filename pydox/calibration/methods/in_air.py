from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Dict, Any, Self, Optional, LiteralString, Callable
import json
from collections import OrderedDict
from dataclasses import dataclass, asdict

import numpy as np
from scipy.optimize import curve_fit

import pydox as do
from pydox._config.config import check_config, Config
from pydox._config.utils import format_value_txt, dict_to_string
from pydox.calibration.core import Workflow
from pydox.calibration.utils import to_list
from pydox.calibration.commodities import ParamsInAir, Data, CoefficientsInAir, FitResults
from pydox.calibration.method import Method
from pydox.core import models


def inair_fit(params: ParamsInAir, data=Any) -> FitResults:
    """This method is low level

    This method must be located away for the 'calibration' submodule, but stay here for dev
    This method should probably be serializable for parallelization

    Parameters
    ----------
    params: ParamsInAir

    data: Any
        Let's place here Argo and reference data needed for this fit
        - PPOX1, PPOX2, NCEP_PPOX

    Returns
    -------
    FitResults
        An dataclass holding all fit results

    Notes
    -----
    4 possible corrections:
    - a gain (G)
    - a gain (G) estimated with CarryOver (C)
    - a gain (G) and a time drift (D)
    - a gain (G) and a time drift (D) estimated with CarryOver (C)

    We use curve_fit for G, D and C estimation.

    The Carryover represents the fact that the InAir Argo PPOX may be polluted by water (waves).
    The CarryOver is determinated by the article 'Oxygen Optode Sensors : Principle, characterization, calibration and application in the Ocean' (Bittig and al. 2018) :
        - G * PPOX_obs_sufr - PPOX_air = C * (G * PPOX_obs_water - PPOX_air)

    """
    # Read data from input:
    PPOX1 = data['PPOX1']
    PPOX2 = data['PPOX2']
    NCEP_PPOX = data['NCEP_PPOX']

    # Depending on parameters, we select a model and set arguments for curve_fit:
    if not params.fit_drift:
        if params.carryover:
            f = models.Gain_CarryOver
            xdata = [PPOX1, PPOX2]
            ydata = NCEP_PPOX
            p0 = [params.initial_gain.value, params.initial_carryover.value]
        else:
            f = models.Gain
            xdata = PPOX1 / PPOX1
            ydata = NCEP_PPOX / PPOX1
            p0 = params.initial_gain.value
    else:
        raise NotImplementedError(f"params.fit_drift = {params.fit_drift}")

    # Then we can call curve_fit:
    # Assumes ``ydata = f(xdata, *params) + eps``.
    #     f : callable
    #     The model function, f(x, ...). It must take the independent
    #     variable as the first argument and the parameters to fit as
    #     separate remaining arguments.
    # xdata : array_like
    #     The independent variable where the data is measured.
    #     Should usually be an M-length sequence or an (k,M)-shaped array for
    #     functions with k predictors, and each element should be float
    #     convertible if it is an array like object.
    # ydata : array_like
    #     The dependent data, a length M array - nominally ``f(xdata, ...)``.
    # p0 : array_like, optional
    #     Initial guess for the parameters (length N). If None, then the
    #     initial values will all be 1 (if the number of parameters for the
    #     function can be determined using introspection, otherwise a
    #     ValueError is raised).
    fit_results, covariance, info, mesg, ier = curve_fit(
        f, xdata, ydata, p0=p0, nan_policy="omit", full_output=True
    )

    # And fill in results for output:
    c = {}
    c['gain'] = Data(fit_results[0], np.sqrt(np.diag(covariance))[0])

    if params.carryover:
        c['carryover'] = Data(fit_results[1], np.sqrt(np.diag(covariance))[1])

    coefs = CoefficientsInAir(**c)

    fit_data = {"R2": 0.9999, "uid": params.uid}

    # Finally gather all data:
    return FitResults(coefs=coefs, fit_data=fit_data)


class MethodInAir(Method):
    rcgroup = "in_air"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Check if we have everything we need in the configuration to run the method:
        # Check reference data access:
        ...
        # Check something else ?
        ...

    def _repr_params(self) -> list[str]:
        """Return a description of parameters for the 'in_air' method"""
        summary = []
        for param in ["carryover"]:
            value = self._mparam(param)
            summary += [f"  {param}: {format_value_txt(value)}"]

        [summary.append(line) for line in self._repr_dataset()]

        return summary

    def _flatten_configs(self) -> OrderedDict[int, dataclass]:
        """Define the entire configuration space to explore with the 'in_air' method"""
        configs, icfg = OrderedDict(), 0
        for fit_drift in to_list(self._sparam("fit_drift")):
            for carryover in to_list(self._mparam("carryover")):
                for ds in to_list(self._mparam("dataset")):
                    p = ParamsInAir(
                        fit_drift=fit_drift,
                        initial_gain=Data(self._sparam("initial_guess.gain"), 0.0),
                        initial_drift=Data(self._sparam("initial_guess.drift"), 0.0),
                        carryover=carryover,
                        dataset=ds,
                        src=self._mparam(f"data.{ds}.src"),
                    )

                    # plist.append(asdict(p))
                    # configs[icfg] = asdict(p)  # Not sure what to carry in here...
                    configs[icfg] = p  # let's keep a dataclass
                    icfg += 1
        return configs

    def fit(self, argofloat_obj: Optional[Any] = None) -> Self:
        """Compute calibration coefficients for all possible configuration set and some Argo float"""

        # We first need to load data that will be used to fit:
        # Data should probably be loaded BEFORE fit to be shared with all concurrent computations

        if self._mparam("dataset") == "ncep":
            # dsair, dsinwater = get_argo_data_for_NCEP(
            #     ds_argo_Rtraj,
            #     ds_argo_Sprof,
            #     which_var,
            #     code_inair,
            #     code_inwater,
            #     min_pres,
            #     max_pres,
            # )
            # argofloat_obj = {
            #     'PPOX1': np.random.random_sample((n,)),
            #     'PPOX2': np.random.random_sample((n,)),
            #     'NCEP_PPOX': np.random.random_sample((n,)),
            # }
            # print(
            #     f"Loaded {self._mparam('data.ncep.name')} data from src={self._mparam('data.ncep.src')}"
            # )
            ...
        else:
            raise NotImplementedError(f"dataset={self._mparam('dataset')}")

        # PPOX1 = dsair["PPOX_DOXY"].values
        # PPOX2 = dsinwater["PPOX_DOXY"].values

        # Execute sequential & ordered computations:
        results = OrderedDict()
        for iset, params in self.configs.items():
            r: Dict[Any, Any] = inair_fit(params=params, data=argofloat_obj)
            # coefs: CoefficientsInAir = r["coefs"]
            # fit_data: Dict[Any, Any] = r["fit_data"]
            results[iset] = r

        return results
