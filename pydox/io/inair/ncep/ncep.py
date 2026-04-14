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


    m1 = ds_ncep['air'].isnull()
    m2 = ds_ncep['slp'].isnull()
    m3 = ds_ncep['rhum'].isnull()

    if ((m1 != m2) | (m1 != m3)).any().compute():
        raise ValueError(f"The 3 variables (air/rhum/slp) don't have the NaN at the same time. Check your NCEP files")

    return ds_ncep