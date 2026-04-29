from typing import Any, Optional

import logging

import xarray as xr
import argopy as ar

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParamsInAir
from pydox.io.argo.facade import get_argo_data_for_in_air_method
from pydox.io.ncep.facade import get_ncep_data_for_in_air_method

log = logging.getLogger("pydox.calibration.methods.utils")


def get_atmospheric_data_for_in_air_method(
    argo_data: dict[str, xr.Dataset | Any],
    config: Config,
    params: Optional[ParamsInAir] = None,
    debug_plot: bool = False,
) -> dict[str, Any]:
    """Load atmospheric reference data

    #todo This function could be refactored in pydox.calibration.methods.in_air
    """
    dataset: str = do.get_params("calibration_methods.in_air.dataset", config=config)

    if dataset == "ncep":
        data = get_ncep_data_for_in_air_method(
            argo_data, config, params, debug_plot=debug_plot
        )
    else:
        raise NotImplementedError(f"No implementation to load dataset={dataset}")

    return data


def get_data_for_one_parameterset_for_in_air_method(
    a_float: ar.ArgoFloat,
    config: Config,
    params: ParamsInAir,
    iset: int,
    debug_plot: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Load and process all data (Argo and atmosphere) required for a single fit

    All downstream methods should rely on values from the `params` argument first, and then on values from `config`.
    We use both because some settings may not be available in the `params` attributes.

    #todo This function could be refactored in pydox.calibration.methods.in_air

    Parameters
    ----------
    a_float: ar.ArgoFloat
    config: Config
    params: ParamsInAir
    iset: int

    debug_plot: bool, optional, default=False

    Returns
    -------
    iset, data
    """
    data: dict[str, Any] = {
        "PPOX1": None,
        "PPOX2": None,
        "REF_PPOX": None,
    }  # Collect obj for output

    # Load Argo float data:
    this_argo = get_argo_data_for_in_air_method(
        a_float, config, params, debug_plot=debug_plot
    )
    data["PPOX1"] = this_argo["ds_inair"]["PPOX_DOXY"].values
    data["PPOX2"] = this_argo["ds_inwater"]["PPOX_DOXY"].values

    # Load Atmospheric data:
    this_atm = get_atmospheric_data_for_in_air_method(
        this_argo, config, params, debug_plot=debug_plot
    )
    data["REF_PPOX"] = this_atm["REF_PPOX"]

    #
    return iset, data
