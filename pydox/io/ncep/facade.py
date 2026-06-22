from typing import Any, Optional
import logging
from pathlib import Path

import numpy as np
import xarray as xr

from pydox.io.argo.types import ArgoDataForInAir
from pydox.io.inair.ncep.ncep import open_ncep, interp_NCEP_on_ARGO


log = logging.getLogger("pydox.io.ncep.facade")


def watervapor(T : xr.DataArray,S: xr.DataArray)->xr.DataArray:
    """ Function to calculate watervapor from Temperature and Salinity

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
    pw=(np.exp(24.4543-(67.4509*(100/(T+273.15)))-(4.8489*np.log(((273.15+T)/100)))-0.000544*S))
    return pw


def calcul_NCEP_PPOX(argo_data_for_air : ArgoDataForInAir, ds_ncep_interp : xr.Dataset,optode_height:float = 0.2,z0q:float = 1e-4) -> np.ndarray:
    bid=watervapor(argo_data_for_air.in_water['TEMP'],argo_data_for_air.in_water['PSAL'])
    SSph20 = bid * 1013.25 #mbar, seasurface water vapor pressure
    ncep_phum = watervapor(ds_ncep_interp['air'].values,0) * ds_ncep_interp['rhum'].values/100*1013.25 #ncep water vapor pressure
    ncep_phum_optode_height = (SSph20.values + (ncep_phum - SSph20.values) * np.log(np.abs(optode_height)/z0q)/np.log(10/z0q))
    ncep_Po2 = (ds_ncep_interp['slp'].values - ncep_phum_optode_height) * 0.20946

    return ncep_Po2

def get_ncep_data_for_in_air_method(
    argo_data_for_air: ArgoDataForInAir,
    optode_height : float,
    #src: str | Path,
    name: Optional[str] = None,
    debug_plot: bool = False,
) -> dict[str, Any]:
    """

    Parameters
    ----------
    argo_data: ArgoDataForInAir
        A dataclass as output from the :func:`do.calibration.methods.in_air.utils.get_argo_data_for_in_air_method` function.
    name: Optional[str]
        NCEP nickname to use.
    src: str | Path
        Source of the NCEP dataset. This can be a string or a :class:`Path` object.
    debug_plot: bool = False

    Returns
    -------
    dict[str, Any]
    """
    name: str = "NCEP" if name is None else name

    # Init output obj:
    data: dict[str, Any] = {"REF_PPOX": None}

    ds_ncep = open_ncep()
    coord_argo = {'lon' : argo_data_for_air.in_air['LONGITUDE'],'lat':argo_data_for_air.in_air['LATITUDE'],'time':argo_data_for_air.in_air['JULD']}
    ds_ncep_interp = interp_NCEP_on_ARGO(ds_ncep,coord_argo)    # todo Implement real NCEP data loading here
    data["REF_PPOX"] = calcul_NCEP_PPOX(argo_data_for_air, ds_ncep_interp,optode_height)
    #
    return data
