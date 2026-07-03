import pytest
import xarray as xr
import numpy as np
import pydox as do
from pydox.io.ncep import facade, utils


def create_dataset_for_test_interp() -> xr.Dataset:
    lon = xr.DataArray([0, 1], dims="lon")
    lat = xr.DataArray([0, 1], dims="lat")
    time = xr.DataArray([0, 1], dims="time")

    # data = np.ones((2,2,2))
    data = np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]])
    ds = xr.Dataset(
        {
            "slp": (("time", "lat", "lon"), data.copy()),
            "air": (("time", "lat", "lon"), data.copy()),
            "rhum": (("time", "lat", "lon"), data.copy()),
        },
        coords={"lon": lon, "lat": lat, "time": time},
    )

    ds["slp"].attrs["units"] = "Pascals"
    ds["air"].attrs["units"] = "degK"

    return ds


def create_coord_for_test_interp():
    return {
        "lon": xr.DataArray([0.5], dims="points"),
        "lat": xr.DataArray([0.5], dims="points"),
        "time": xr.DataArray([0.5], dims="points"),
    }


def test_dir_ncep_not_defined(monkeypatch):
    monkeypatch.setattr(do, "get_params", lambda x: None)

    with pytest.raises(ValueError):
        facade.open_ncep()


def test_dir_ncep_not_valid(monkeypatch):
    monkeypatch.setattr(do, "get_params", lambda x: "/bidon")
    with pytest.raises(ValueError):
        facade.open_ncep()


def test_dir_ncep_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(do, "get_params", lambda x: tmp_path)
    monkeypatch.setattr(facade.xr, "open_mfdataset", lambda files: None)
    (tmp_path / "file.nc").touch()

    fake_ds = create_dataset_for_test_interp()
    monkeypatch.setattr(facade.xr, "open_mfdataset", lambda files: fake_ds)
    facade.open_ncep()


def test_dir_var_ncep_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(do, "get_params", lambda x: tmp_path)

    (tmp_path / "file.nc").touch()
    fake_ds = xr.Dataset(
        {
            "air1": (("x",), [1.0]),
            "slp1": (("x",), [2.0]),
            "rhum1": (("x",), [3.0]),
        }
    )

    monkeypatch.setattr(facade.xr, "open_mfdataset", lambda files: fake_ds)
    with pytest.raises(ValueError):
        facade.open_ncep()


def test_dir_ncep_no_ncfiles(monkeypatch, tmp_path):
    empty_dir = tmp_path / "bid"
    empty_dir.mkdir()
    monkeypatch.setattr(do, "get_params", lambda x: empty_dir)
    with pytest.raises(ValueError):
        facade.open_ncep()


def test_ncep_slp_units():
    ds_ncep = create_dataset_for_test_interp()
    ds_ncep["slp"].attrs["units"] = "hPa"
    with pytest.raises(ValueError):
        facade.open_ncep(refresh=True)


def test_ncep_air_units():
    ds_ncep = create_dataset_for_test_interp()
    ds_ncep["air"].attrs["units"] = "Celsius"
    with pytest.raises(ValueError):
        facade.open_ncep(refresh=True)


def test_ncep_interp_ok():
    ds_ncep = create_dataset_for_test_interp()
    coord_argo = create_coord_for_test_interp()
    ds_interp = utils.interp_NCEP_on_ARGO(ds_ncep, coord_argo)

    assert "slp" in ds_interp
    assert "air" in ds_interp
    assert "rhum" in ds_interp

    assert ds_interp["slp"] == 4.5
    assert ds_interp["air"] == 4.5
