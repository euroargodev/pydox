from copy import deepcopy

import pydox as do
import numpy as np
import xarray as xr

from pydox.reporting.logs import getLogger
from pydox.io.argo.types import ArgoDataForInAir
from pydox.utils.chemistry import watervapor

log = getLogger("pydox.io.ncep.utils", context_level=0)


def compute_NCEP_PPOX(
    argo_data_for_air: ArgoDataForInAir, ds_ncep_interp: xr.Dataset, z0q: float = 1e-4
) -> np.ndarray:
    """

    Parameters
    ----------
    argo_data_for_air
    ds_ncep_interp
    z0q

    Returns
    -------

    """
    if argo_data_for_air.optode_height is None:
        log.info(
            f"Set optode_height to configuration value: {do.get_params('argo.optode_height')}"
        )
        argo_data_for_air.optode_height = do.get_params("argo.optode_height")

    bid = watervapor(
        argo_data_for_air.in_water["TEMP"], argo_data_for_air.in_water["PSAL"]
    )
    SSph20 = bid * 1013.25  # mbar, sea surface water vapor pressure
    ncep_phum = (
        watervapor(ds_ncep_interp["air"].values, 0.0)
        * ds_ncep_interp["rhum"].values
        / 100
        * 1013.25
    )  # ncep water vapor pressure
    ncep_phum_optode_height = SSph20.values + (ncep_phum - SSph20.values) * np.log(
        np.abs(argo_data_for_air.optode_height) / z0q
    ) / np.log(10 / z0q)
    ncep_Po2 = (ds_ncep_interp["slp"].values - ncep_phum_optode_height) * 0.20946

    return ncep_Po2


def interp_NCEP_on_ARGO(
    ds_ncep: xr.Dataset, coord_argo: dict[str, xr.DataArray]
) -> xr.Dataset:
    """Interpolate NCEP :class:`xr.Dataset` on ARGO coordinates (lon/lat/time).

    Parameters
    ----------
    ds_ncep: xr.Dataset
        NCEP class:`xr.Dataset` with 'slp,',air,'rhum' variables
    coord_argo: dict[str, xr.DataArray]
        ARGO coordinates to interpolate NCEP on. Coordinates are given as a dictionary
        with 'lon','lat' and 'time' keys, values are :class:`xr.DataArray`.

    Returns
    -------
    :class:`xr.Dataset`
        NCEP variables interpolated on ARGO coordinates
    """
    # We work with a deepcopy to do not modify the original NCEP dataset
    ds_ncep_interp = deepcopy(ds_ncep)
    ds_ncep_interp = ds_ncep_interp.interp(
        lat=coord_argo["lat"], lon=coord_argo["lon"], time=coord_argo["time"]
    )

    # todo : Test if each ARGO Position is associated to each NCEP data.
    # Maybe not to do in that function. Create a dedicated function ?

    return ds_ncep_interp
