import sys
import os
import pytest
from matplotlib.testing import subprocess_run_for_testing

from pydox._config.config import _get_xdg_config_dir, get_configdir

def test_get_xdg_config_dir():
    assert isinstance(_get_xdg_config_dir(), str)

def test_get_configdir():
    pass

def test_importable_with_no_home(tmp_path):
    subprocess_run_for_testing(
        [sys.executable, "-c",
         "import pathlib; pathlib.Path.home = lambda *args: 1/0; "
         "import pydox"],
        env={**os.environ, "PYDOXCONFIGDIR": str(tmp_path)}, check=True)

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_configdir_uses_localappdata_on_windows(tmp_path):
    """Test that on Windows, config/cache dir uses LOCALAPPDATA for fresh installs.

    Adapted from Matplotlib:
    https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/tests/test_matplotlib.py#L100
    """
    localappdata = tmp_path / "AppData/Local"
    localappdata.mkdir(parents=True)
    # Set USERPROFILE to tmp_path so the old location check finds nothing
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    proc = subprocess_run_for_testing(
        [sys.executable, "-c",
         "import pydox; print(pydox.get_configdir())"],
        env={**os.environ, "LOCALAPPDATA": str(localappdata),
             "USERPROFILE": str(fake_home), "PYDOXCONFIGDIR": ""},
        capture_output=True, text=True, check=True)

    configdir = proc.stdout.strip()
    # On Windows with no existing old config, should use LOCALAPPDATA\pydox
    assert configdir == str(localappdata / "pydox")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
def test_configdir_uses_userprofile_on_windows_if_exists(tmp_path):
    """Test that on Windows, config/cache dir uses %USERPROFILE% if .pydox exists.

    Adapted from Matplotlib:
    https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/tests/test_matplotlib.py#L121
    """
    localappdata = tmp_path / "AppData/Local"
    localappdata.mkdir(parents=True)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    old_configdir = fake_home / ".pydox"
    old_configdir.mkdir()

    proc = subprocess_run_for_testing(
        [sys.executable, "-c",
         "import pydox; print(pydox.get_configdir())"],
        env={**os.environ, "LOCALAPPDATA": str(localappdata),
             "USERPROFILE": str(fake_home), "PYDOXCONFIGDIR": ""},
        capture_output=True, text=True, check=True)

    configdir = proc.stdout.strip()
    # On Windows with existing old config, should continue using it
    assert configdir == str(old_configdir)