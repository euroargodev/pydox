from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from pydox.commodities import (
    Data,
    ParamsInAir,
    CoefficientsInAir,
    FitResult,
)
from pydox.core import models


def inair_fit(params: ParamsInAir, data=Any) -> FitResult:
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
    FitResult
        An dataclass holding fit result for a single set of parameters

    Notes
    -----
    4 possible corrections:
    - a gain (G)
    - a gain (G) estimated with CarryOver (C)
    - a gain (G) and a time drift (D)
    - a gain (G) and a time drift (D) estimated with CarryOver (C)

    We use curve_fit for G, D and C estimation.

    The Carryover represents the fact that the InAir Argo PPOX may be polluted by water (waves).
    The CarryOver is determined by the article 'Oxygen Optode Sensors : Principle, characterization, calibration and application in the Ocean' (Bittig and al. 2018) :
        - G * PPOX_obs_sufr - PPOX_air = C * (G * PPOX_obs_water - PPOX_air)

    """
    # Read data from input object:
    PPOX1 = data["PPOX1"]
    PPOX2 = data["PPOX2"]
    NCEP_PPOX = data["NCEP_PPOX"]

    # Depending on parameters, we select a model and set arguments for curve_fit:
    if not params.fit_drift:
        if params.carryover:
            f = models.Gain_CarryOver
            xdata = [PPOX1, PPOX2]
            ydata = NCEP_PPOX
            p0 = [params.initial_gain.value, params.initial_carryover.value]  # G/C
        else:
            f = models.Gain
            xdata = PPOX1 / PPOX1
            ydata = NCEP_PPOX / PPOX1
            p0 = params.initial_gain.value  # G
    else:
        raise NotImplementedError(f"params.fit_drift = {params.fit_drift}")
        # if params.carryover:
        #     f = models.Gain_Derive_CarryOver
        #     xdata = [PPOX1, PPOX2, delta_T_NCEP]
        #     ydata = NCEP_PPOX
        #     p0 = [params.initial_gain.value, params.initial_carryover.value, params.initial_drift.value] # G/C/D
        # else:
        #     f = models.Gain_Derive
        #     xdata = [PPOX1 / PPOX1, delta_T_NCEP]
        #     ydata = NCEP_PPOX / PPOX1
        #     p0 = [params.initial_gain.value, params.initial_drift.value] # G/D

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
    c["gain"] = Data(fit_results[0], np.sqrt(np.diag(covariance))[0])

    if params.carryover:
        c["carryover"] = Data(fit_results[1], np.sqrt(np.diag(covariance))[1])

    coefs = CoefficientsInAir(**c)
    fit_data = {
        "R2": float(np.random.random_sample(1)[0]),  # Dummy
        "uid": params.uid
    }

    # Finally gather all data:
    return FitResult(coefs=coefs, fit_data=fit_data)

