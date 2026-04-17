import pydox
import pydox as do
import pydox.io.inair.ncep.ncep as ncep
import pytest
import xarray as xr

def test_dir_ncep_not_defined(monkeypatch):
    monkeypatch.setattr("pydox.io.inair.ncep.ncep.do.get_params", lambda x: None)
    with pytest.raises(ValueError):
        ncep.open_ncep()

def test_dir_ncep_not_valid(monkeypatch):
    monkeypatch.setattr("pydox.io.inair.ncep.ncep.do.get_params", lambda x: "/bidon")
    with pytest.raises(ValueError):
        ncep.open_ncep()

def test_dir_ncep_exists(monkeypatch,tmp_path):
    monkeypatch.setattr('pydox.io.inair.ncep.ncep.do.get_params' , lambda x: tmp_path)
    monkeypatch.setattr(
        "pydox.io.inair.ncep.ncep.xr.open_mfdataset",
        lambda files: None
    )
    (tmp_path / "file.nc").touch()
    fake_ds = xr.Dataset({
        "air": (("x",), [1.0]),
        "slp": (("x",), [2.0]),
        "rhum": (("x",), [3.0]),
    })

    monkeypatch.setattr(
        "pydox.io.inair.ncep.ncep.xr.open_mfdataset",
        lambda files: fake_ds
    )
    ncep.open_ncep()

def test_dir_var_ncep_missing(monkeypatch, tmp_path):
    monkeypatch.setattr('pydox.io.inair.ncep.ncep.do.get_params', lambda x: tmp_path)

    (tmp_path / "file.nc").touch()
    fake_ds = xr.Dataset({
            "air1": (("x",), [1.0]),
            "slp1": (("x",), [2.0]),
            "rhum1": (("x",), [3.0]),
    })

    monkeypatch.setattr(
            "pydox.io.inair.ncep.ncep.xr.open_mfdataset",
            lambda files: fake_ds
    )
    with pytest.raises(ValueError):
        ncep.open_ncep()

def test_dir_ncep_no_ncfiles(monkeypatch,tmp_path):
    empty_dir = tmp_path /"bid"
    empty_dir.mkdir()
    monkeypatch.setattr(
        "pydox.io.inair.ncep.ncep.do.get_params",
        lambda x : empty_dir
    )
    with pytest.raises(ValueError):
        ncep.open_ncep()
