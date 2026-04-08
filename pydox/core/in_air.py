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
    """Generic in-air calibration computation method

    This method is low level and should not be called by users.
    This method must NOT rely on anything from the 'calibration' submodule.
    This method should probably be serializable for parallelization.

    Parameters
    ----------
    params: ParamsInAir
        A set of parameters defining the calibration to compute.

    data: Any
        This object must contain ALL required data for the computation, from an Argo float and from Reference data.
        This would typically provide data like: PPOX1, PPOX2, REF_PPOX arrays.

    Returns
    -------
    FitResult
        An dataclass holding one fit result for a single set of parameters

    Notes
    -----
    Depending on `ParamsInAir`, this function can compute 4 possible calibrations:
    - a gain (G)
    - a gain (G) estimated with CarryOver (C)
    - a gain (G) and a time drift (D)
    - a gain (G) and a time drift (D) estimated with CarryOver (C)

    We use :function:`scipy.optimize.curve_fit` for G, D and C estimation.

    Notes
    -----
    _Carryover_ represents the fact that the in-air Argo PPOX may be polluted by water (waves).

    It is determined according to Bittig and al. 2018 [1]_ as:

    .. math::
        - G * PPOX_{obs_surf} - PPOX_{air} = C * \left(G * PPOX_{obs_water} - PPOX_{air} \right)

    References
    ----------
    .. [1] Bittig and al. 2018: 'Oxygen Optode Sensors : Principle, characterization, calibration and application in the Ocean'

    """
    # Read data from input object:
    PPOX1 = data["PPOX1"]
    PPOX2 = data["PPOX2"]
    REF_PPOX = data[
        "REF_PPOX"
    ]  # REF_PPOX is a generic term to replace NCEP_PPOX and ERA5_PPOX

    # Depending on parameters, we select a model and set arguments for curve_fit:
    if not params.fit_drift:
        if params.carryover:
            f = models.Gain_CarryOver
            xdata = [PPOX1, PPOX2]
            ydata = REF_PPOX
            p0: models.Array = np.array(
                [params.initial_gain.value, params.initial_carryover.value]
            )  # G/C
        else:
            f = models.Gain
            xdata = PPOX1 / PPOX1
            ydata = REF_PPOX / PPOX1
            p0: models.Array = np.array(params.initial_gain.value)  # G
    else:
        raise NotImplementedError(f"params.fit_drift = {params.fit_drift}")
        # if params.carryover:
        #     f = models.Gain_Derive_CarryOver
        #     xdata = [PPOX1, PPOX2, delta_T_REF]
        #     ydata = REF_PPOX
        #     p0 = [params.initial_gain.value, params.initial_carryover.value, params.initial_drift.value] # G/C/D
        # else:
        #     f = models.Gain_Derive
        #     xdata = [PPOX1 / PPOX1, delta_T_REF]
        #     ydata = REF_PPOX / PPOX1
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
    # c["gain"] = Data(fit_results[0], np.sqrt(np.diag(covariance))[0])
    c["gain"] = Data(
        fit_results[0], params.dummy
    )  # Replace error with dummy var. to track stuff in dev.
    c["gain"] = Data(
        1.0 + params.initial_gain.value, params.dummy
    )  # Use dummy value to check for cumulative gain feature and replace error with dummy var. to track stuff in dev.

    if params.carryover:
        c["carryover"] = Data(fit_results[1], np.sqrt(np.diag(covariance))[1])

    coefs = CoefficientsInAir(**c)
    fit_data = {
        "R2": float(np.random.random_sample(1)[0]),
        "uid": params.uid,
        "initial gain": params.initial_gain.value,
    }  # Dummy

    # Finally gather and return all results into a controlled object:
    return FitResult(coefs=coefs, fit_data=fit_data)
