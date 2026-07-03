import numpy as np
import xarray as xr


def watervapor(T: xr.DataArray, S: xr.DataArray | float) -> xr.DataArray:
    """Function to calculate water vapor from Temperature and Salinity

    Parameters
    ----------
    T : xr.DataArray
        Temperature
    S : xr.DataArray
        Salinity

    Returns
    -------
    pw : xr.DataArray
        WaterVapor
    """
    pw = np.exp(
        24.4543
        - (67.4509 * (100 / (T + 273.15)))
        - (4.8489 * np.log(((273.15 + T) / 100)))
        - 0.000544 * S
    )
    return pw
