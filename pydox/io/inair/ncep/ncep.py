"""
NCEP Module
"""
import pydox as do
import glob
import xarray as xr

def open_ncep()->xr.dataset.Dataset:
    """
    Opens NCEP files from the NCEP directory defined in the user configuration.
    Returns a dataset xarray with the air/rhum and slp variables.
    """
    try:
        rep_data_ncep = do.get_params('calibration_methods.in_air.data.ncep.src')
    except:
        raise ValueError("NCEP directory not defined")

    if not rep_data_ncep:
        raise ValueError("NCEP directory not defined")

    fic_ncep = glob.glob(rep_data_ncep + '*nc')

    if not fic_ncep:
        raise ValueError("No NCEP files found")

    ds_ncep = xr.open_mfdataset(fic_ncep)

    needed = ['slp', 'air', 'rhum']
    not_available = [v for v in needed if v not in ds_ncep]

    if not_available:
        raise KeyError(f"No NCEP files availables for : {not_available}")

    return ds_ncep