"""
NCEP Module
"""
import pydox as do
from pathlib import Path
import xarray as xr

def open_ncep()->xr.Dataset:
    """
    Opens NCEP files from the NCEP directory defined in the user configuration.
    Returns a dataset xarray with the air/rhum and slp variables.

    This function assumes that the NCEP directory is defined in the user configuration
     (in calibration_methods.in_air.data.ncep.src).
     All the NCEP files needed (air.sig995.YYYY.nc, rhum.sig995.YYYY.nc, slp.YYYY.nc) must exist in this directory,
     at the root level.
    """

    src_data_ncep = do.get_params('calibration_methods.in_air.data.ncep.src')

    if not src_data_ncep:
        raise ValueError("The NCEP data source parameter is not defined in the configuration. Please set 'calibration_methods.in_air.data.ncep.src' appropriately.")

    if not Path(src_data_ncep).is_dir():
        raise ValueError(f"The NCEP data source parameter {src_data_ncep} does not point toward a valid directory.")

    files_ncep = [p.resolve() for p in list(Path(src_data_ncep).glob('*.nc'))]

    if len(files_ncep)==0:
        raise ValueError(f"No NCEP files found in the directory {src_data_ncep}")

    ds_ncep = xr.open_mfdataset(files_ncep)

    needed = ['slp', 'air', 'rhum']
    not_available = [v for v in needed if v not in ds_ncep]

    if not_available:
        raise ValueError(f"No NCEP files availables for : {not_available} in {src_data_ncep}")

#
# this takes a long time.
# Maybe this is not in this file that we must check that we associate a reference data point with each floating-point data point in the fit.
# We'll have to see where it makes the most sense to do that...
# For now, we leave it as is
# todo remove these lines
    m1 = ds_ncep['air'].isnull()
    m2 = ds_ncep['slp'].isnull()
    m3 = ds_ncep['rhum'].isnull()

    if ((m1 != m2) | (m1 != m3)).any().compute():
        raise ValueError(f"The 3 variables (air/rhum/slp) don't have the NaN at the same time. Check your NCEP files")

    return ds_ncep


def interp_NCEP_on_ARGO(ds_ncep: xr.Dataset, coord_argo: dict) -> xr.Dataset:
    """
    Function to interpolate a NCEP xarray dataset containing variables 'slp,',air,'rhum' on
    ARGO cooordinates (lon/lat/time).
    The ARGO coordinates are given in a dictionnary with the keys : 'lon','lat','time'.
    The associated values are  DataArray.

    Returns a xarray Dataset with the NCEP variables interpolated on ARGO lon/lat/time.

    """
    # Force NCEP lon to be in [-180 180] as the ARGO longitude
    ds_ncep['lon'] = xr.where(ds_ncep['lon'] > 180, ds_ncep['lon'] - 360, ds_ncep['lon'])

    ds_ncep_interp = ds_ncep.interp(lat=coord_argo['lat'], lon=coord_argo['lon'], time=coord_argo['time'])
    #
    # Units Conversion
    #
    if ds_ncep_interp['slp'].units == 'Pascals':
        # Transform Pascal to HectoPascal/Millibar
        print(f"NCEP slp : Conversion Pascals to HectoPascal/Millibar for NCEP PPOX computing")
        ds_ncep_interp['slp'] = ds_ncep_interp['slp'] / 100
    else:
        raise ValueError(f"the NCEP variable 'slp' must be in Pascals units")

    if ds_ncep_interp['air'].units == 'degK':
        # Transform Pascal to HectoPascal/Millibar
        print(f"NCEP air : Conversion Kelvin to Celsius for NCEP PPOX computing")
        ds_ncep_interp['air'] = ds_ncep_interp['air'] - 273.15
    else:
        raise ValueError(f"the NCEP variable 'air' must be in Celsius units")

    # todo : Test if each ARGO Position is associated to each NCEP data.
    # Maybe not to do in that function. Create a dedicated function ?

    return ds_ncep_interp