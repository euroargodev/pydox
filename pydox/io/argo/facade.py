"""
This module provide facades to be used in calibration methods

These facades convert settings from high-level object like the full configuration or a ParameterSet instance
to simple arguments consumed by specification methods.

"""

from typing import Optional
import logging

import xarray as xr
import argopy as ar

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParameterSet


from pydox.io.argo.types import MultiProfData, TrajData
from pydox.io.argo.utils import (
    semantic_cycle2values,
    parameter_selection_rtraj,
    parameter_selection_sprof,
)
from pydox.io.argo.spec import _get_argo_data_for_in_air_method


log = logging.getLogger("pydox.io.argo.facade")


def get_argo_data_for_in_air_method(
    a_float: ar.ArgoFloat,
    config: Config,
    params: Optional[ParameterSet] = None,
    debug_plot: bool = False,
) -> dict[str, xr.Dataset]:
    """Load Argo float data to correct oxygen with atmospheric data (in-air method)

    We load data from all cycle numbers and cache results.

    Adapted from `m_argo_data.get_argo_data_for_NCEP()`
    """

    # Read parameters from the configuration object:

    min_pres: float = do.get_params(
        "argo.in_water_salinity.min_pressure", config=config
    )
    max_pres: float = do.get_params(
        "argo.in_water_salinity.max_pressure", config=config
    )
    in_air_codes: list[int] = do.get_params("argo.codes.in_air", config=config)
    in_water_codes: list[int] = do.get_params("argo.codes.in_water", config=config)
    which_psal: int = do.get_params("argo.use", config=config)

    # Read other parameters from the ParameterSet object:
    if params is None:
        cycles: list[int] = semantic_cycle2values(input=config, a_float=a_float)
    else:
        cycles: list[int] = semantic_cycle2values(input=params, a_float=a_float)

    # Read parameters from the ArgoFloat instance:
    # optode_height: float = a_float.launchconfig["OptodeVerticalPressureOffset_dbar"]

    # Now we can load data and select variables:

    # GDAC Argo data are loaded from file (local or remote) when accessing 'Sprof' and 'Rtraj' from the ArgoFloat dataset method:
    Sprof: xr.Dataset = a_float.dataset("Sprof")
    Rtraj: xr.Dataset = a_float.dataset("Rtraj")

    # From raw GDAC xr.DataSet objects, we sub-select only variables that we really need to work with:
    # (this makes data processing by specification method easier)
    Sprof: MultiProfData = parameter_selection_sprof(Sprof)
    Rtraj: TrajData = parameter_selection_rtraj(Rtraj)

    return _get_argo_data_for_in_air_method(
        min_pres=min_pres,
        max_pres=max_pres,
        in_air_codes=tuple(in_air_codes),
        in_water_codes=tuple(in_water_codes),
        which_psal=which_psal,
        cycles=tuple(cycles),
        Sprof=Sprof,
        Rtraj=Rtraj,
        debug_plot=debug_plot,
    )
