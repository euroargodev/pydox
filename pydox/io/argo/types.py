from typing import Annotated
import xarray as xr
from dataclasses import dataclass


# Type for a xarray object with dimensions N_PROF and N_LEVELS
MultiProfData = Annotated[
    xr.Dataset | xr.DataArray,
    {"dims": ("N_PROF", "N_LEVELS")},  # Metadata (not enforced by mypy)
]

# Type for a xarray object with dimensions N_MEASUREMENT
TrajData = Annotated[
    xr.Dataset | xr.DataArray,
    {"dims": ("N_MEASUREMENT",)},  # Metadata (not enforced by mypy)
]


@dataclass
class ArgoDataForInAir:
    """A placeholder to organize output from :func:`pydox.io.argo.facade.get_argo_data_for_in_air_method`

    Provides: in_air, in_water, Sprof and Rtraj xr.Dataset.

    This is cleaner and easier to discover/document than a dictionary
    """

    in_air: xr.Dataset
    """A xr.Dataset with in-air trajectory data, grouped by cycle numbers"""

    in_water: xr.Dataset
    """A xr.Dataset with in-water trajectory data, grouped by cycle numbers"""

    Sprof: xr.Dataset
    """A xr.Dataset with multi-profile data from the Sprof file"""

    Rtraj: xr.Dataset
    """A xr.Dataset with measurements data from the Rtraj file"""
