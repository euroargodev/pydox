from typing import Any, Optional

import logging

import numpy as np
import xarray as xr
import argopy as ar

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParamsInAir


log = logging.getLogger("pydox.io.ncep.facade")


def get_ncep_data_for_in_air_method(
    argo_data: dict[str, xr.Dataset | Any],
    config: Config,
    params: Optional[ParamsInAir] = None,
    debug_plot: bool = False,
) -> dict[str, Any]:
    """

    Parameters
    ----------
    argo_data: dict
        As output from the `pydox.io.argo.facade.get_argo_data_for_in_air_method()` function.
    config
    params
    debug_plot

    Returns
    -------

    """

    name: str = do.get_params(
        "calibration_methods.in_air.data.ncep.name", config=config
    )

    if params is None:
        src: str = do.get_params(
            "calibration_methods.in_air.data.ncep.src", config=config
        )
    else:
        src: str = params.src

    # Init output obj:
    data: dict[str, Any] = {"REF_PPOX": None}

    # todo Implement real NCEP data loading here

    # Create dummy data:
    data["REF_PPOX"] = np.random.random_sample(
        (len(argo_data["ds_inair"]["PPOX_DOXY"].values),)
    )
    log.info(f"Return dummy data for {name}, based on {src}")

    #
    return data
