from typing import Any, Optional
import logging
from pathlib import Path
import hashlib

import pydox as do
import xarray as xr

from pydox.io.argo.types import ArgoDataForInAir
from pydox.io.ncep.utils import compute_NCEP_PPOX, interp_NCEP_on_ARGO


log = logging.getLogger("pydox.io.ncep.facade")

_ds_NCEP: dict[str, xr.Dataset] = {}
"""Global placeholder for NCEP dataset, avoid multiple load"""


def get_ncep_data_for_in_air_method(
    argo_data_for_air: ArgoDataForInAir,
    # src: str | Path,
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

    # Load NCEP in memory
    # todo This is very time consuming, consider re-designing when the matchup lib. will be available.
    ds_ncep = open_ncep()
    coord_argo = {
        "lon": argo_data_for_air.in_air["LONGITUDE"],
        "lat": argo_data_for_air.in_air["LATITUDE"],
        "time": argo_data_for_air.in_air["JULD"],
    }
    ds_ncep_interp = interp_NCEP_on_ARGO(ds_ncep, coord_argo)
    data["REF_PPOX"] = compute_NCEP_PPOX(argo_data_for_air, ds_ncep_interp)

    return data


def open_ncep(refresh: bool = False) -> xr.Dataset:
    """Load NCEP files from the NCEP directory defined in the user configuration

    Returns a :class:`xr.Dataset` with air, rhum and slp variables.

    This function assumes that the NCEP directory is defined in the user configuration
     ('calibration_methods.in_air.data.ncep.src').

    Assume NCEP files are of the form:

    - air.sig995.YYYY.nc,
    - rhum.sig995.YYYY.nc,
    - slp.YYYY.nc.
    all located at the root level.

    Warnings
    --------
    Original Slp values are expected to be in Pascals and are converted to HPa/Millibar.

    Original Air values are expected to be in kelvins and are converted to degrees Celsius.

    We perform these unit conversions to calculate NCEP PPOX

    Returns
    -------
    :class:`xr.Dataset`
        Full NCEP dataset in memory
    """

    def get_hash(files):
        m = hashlib.sha256()
        for f in files:
            m.update(bytes(str(f), "utf-8"))
        return m.hexdigest()

    src_data_ncep = do.get_params("calibration_methods.in_air.data.ncep.src")

    if not src_data_ncep:
        raise ValueError(
            "The NCEP data source parameter is not defined in the configuration. Please set 'calibration_methods.in_air.data.ncep.src' appropriately."
        )

    if not Path(src_data_ncep).is_dir():
        raise ValueError(
            f"The NCEP data source parameter {src_data_ncep} does not point toward a valid directory."
        )

    files_ncep = [p.resolve() for p in list(Path(src_data_ncep).glob("*.nc"))]
    hash = get_hash(files_ncep)

    if len(files_ncep) == 0:
        raise ValueError(f"No NCEP files found in the directory {src_data_ncep}")

    if refresh or hash not in _ds_NCEP:

        ds_ncep = xr.open_mfdataset(files_ncep)

        needed = ["slp", "air", "rhum"]
        not_available = [v for v in needed if v not in ds_ncep]

        if not_available:
            raise ValueError(
                f"No NCEP files availables for : {not_available} in {src_data_ncep}"
            )

        #
        # this takes a long time.
        # Maybe this is not in this file that we must check that we associate a reference data point with each floating-point data point in the fit.
        # We'll have to see where it makes the most sense to do that...
        # For now, we leave it as is
        # todo remove these lines
        m1 = ds_ncep["air"].isnull()
        m2 = ds_ncep["slp"].isnull()
        m3 = ds_ncep["rhum"].isnull()

        if ((m1 != m2) | (m1 != m3)).any().compute():
            raise ValueError(
                f"The 3 variables (air/rhum/slp) don't have the NaN at the same time. Check your NCEP files"
            )

        #
        # Units Conversion
        #
        if ds_ncep["slp"].units == "Pascals":
            # Transform Pascal to HectoPascal/Millibar
            print(
                f"NCEP slp : Conversion Pascals to HectoPascal/Millibar for NCEP PPOX computing"
            )
            ds_ncep["slp"] = ds_ncep["slp"] / 100
        else:
            raise ValueError(f"NCEP variable 'slp' must be in Pascals units")

        if ds_ncep["air"].units == "degK":
            # Transform Kelvin to Celsius
            print(f"NCEP air : Conversion Kelvin to Celsius for NCEP PPOX computing")
            ds_ncep["air"] = ds_ncep["air"] - 273.15
        else:
            raise ValueError(f"NCEP variable 'air' must be in Kelvin units")

        # Force NCEP lon to be in [-180 180] as the ARGO longitude
        print(f"NCEP longitude : force to be in [-180 180] like ARGO")
        ds_ncep["lon"] = xr.where(
            ds_ncep["lon"] > 180, ds_ncep["lon"] - 360, ds_ncep["lon"]
        )
        # Register to global placeholder:
        _ds_NCEP[hash] = ds_ncep

    return _ds_NCEP[hash]
