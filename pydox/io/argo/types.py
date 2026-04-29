from typing import Annotated
import xarray as xr


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
