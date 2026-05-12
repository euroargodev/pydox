import logging
import sys
import os
import pytest
from pathlib import Path
from matplotlib.testing import subprocess_run_for_testing
from typing import Dict, Any
from IPython.display import HTML
import stat
import re

import pydox as do
from pydox._config.config import (
    _get_xdg_config_dir,
    get_configdir,
    config_files,
    flatten_config_keys,
    overload_config,
    load_factory_config,
    is_config,
    load_configs,
    get_by_path,
    set_by_path,
    _read_only_dotted_params,
    get_params,
    set_params,
    reset_params,
    config_print,
)
from pydox._config.utils import (
    uid,
    runner,
    format_value_txt,
    format_value_html,
)


log = logging.getLogger("pydox.tests.config")


def test_get_xdg_config_dir():
    assert isinstance(_get_xdg_config_dir(), str)


def test_get_configdir(tmp_path):
    cd = get_configdir()
    assert isinstance(cd, str)
    assert os.access(str(cd), os.W_OK)  # Must be writable

    # Get a non-writable folder to trigger the creation of a temp folder:
    try:
        prev = os.environ["PYDOXCONFIGDIR"]
        os.environ.pop("PYDOXCONFIGDIR")
    except:
        prev = "9999"

    os.chmod(tmp_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    os.environ["PYDOXCONFIGDIR"] = str(tmp_path)
    cd = get_configdir()
    assert isinstance(cd, str)
    assert os.access(str(cd), os.W_OK)  # Must be writable

    # Restore PYDOXCONFIGDIR
    if prev != "9999":
        os.environ["PYDOXCONFIGDIR"] = str(prev)


def test_config_files():
    cf = config_files()
    # log.info(cf)
    assert isinstance(cf, list)
    assert all([isinstance(f, Path) for f in cf])

    # Test ensuring no PYDOXRC env is set:
    try:
        PYDOXRC = os.environ["PYDOXRC"]
        os.environ.pop("PYDOXRC")
    except:
        PYDOXRC = "9999"

    proc = subprocess_run_for_testing(
        [sys.executable, "-c", "import pydox; print(pydox.config_files())"],
        env={**os.environ},
        capture_output=True,
        text=True,
        check=True,
    )
    cf = proc.stdout.strip()
    if sys.platform != "win32":
        assert "PosixPath" in cf
    else:
        assert "WindowsPath" in cf

    # Restore PYDOXRC env
    if PYDOXRC != "9999":
        os.environ["PYDOXRC"] = PYDOXRC


def test_flatten_config_keys():
    nested_dict = {
        "Name": "John Doe",
        "Organization": "Ifremer",
        "Contact": {
            "Email": "john.doe@ifremer.com",
            "Phone": "+33 1 23 45 67 89",
            "Address": {
                "Street": "123 Ocean Ave",
                "City": "Brest",
                "Country": "France",
            },
        },
        "Projects": {
            "Current": "Data Science Library",
            "Past": ["Project A", "Project B"],
        },
    }

    keys = flatten_config_keys(nested_dict)
    assert isinstance(keys, list)
    assert all([isinstance(k, str) for k in keys])


def test_overload_config():
    x = {
        "Name": "John Doe",
        "Organization": "Ifremer",
        "Contact": {
            "Email": "john.doe@ifremer.com",
            "Phone": "+33 1 23 45 67 89",
        },
    }
    y = {"Name": "Jane Doe", "Contact": {"Email": "jane.doe@ifremer.com"}}
    z = overload_config(x, y)
    assert z["Name"] == y["Name"]
    assert z["Contact"]["Phone"] == x["Contact"]["Phone"]


def test_load_factory_config():
    assert is_config(load_factory_config())


def test_load_configs():
    cfg = load_configs()
    assert is_config(cfg)


def test_load_configs_error(tmp_path, monkeypatch):
    """Check if an error is raised when trying to merge config files with different versions

    We use a mocked function to return a list of default configuration files with config_files() that
    has a file with an inappropriate version.
    """

    # Define mocked version of the config_files() method
    def mock_config_files() -> list[Path]:
        """Return 2 files, first is factory file, second is a temporary file where we set the version to 9999"""
        fs = config_files()

        tmp_file = tmp_path.joinpath("pydoxrc")
        yml = """
        version: '9999'
        operator:
          name: 'John Doe'
        """
        tmp_file.write_text(yml, encoding="utf-8")

        return [fs[0], tmp_file]

    # Then we mock config_files() to force an error in overload_config():
    with monkeypatch.context() as m:
        m.setattr(
            do._config.config, "config_files", mock_config_files
        )  # So that load_configs will call the mock
        with pytest.raises(ValueError):
            load_configs()


@pytest.fixture
def base_config() -> Dict[str, Any]:
    """Fixture providing a base configuration object for testing."""
    return {
        "version": "0.1",
        "name": "My dummy configuration",
        "argo": {
            "src": "https://data-argo.ifremer.fr",
            "qcflags": {
                "pres": [1, 2, 8],
                "psal": [1, 2, 8],
                "temp": [1, 2, 8],
                "doxy": [1, 2, 8, 3],
            },
        },
    }


def test_get_by_path(base_config):
    """
    This test assumes that a configuration is a real nested dictionary.
    This could change in the future, and test should be updated.
    """
    assert get_by_path(base_config, "name") == base_config["name"]
    assert get_by_path(base_config, "argo.src") == base_config["argo"]["src"]


def test_set_by_path(base_config):
    set_by_path(base_config, "name", "Hello world")
    assert get_by_path(base_config, "name") == "Hello world"

    set_by_path(base_config, "argo.src", "http://hello.world")
    assert get_by_path(base_config, "argo.src") == "http://hello.world"

    with pytest.raises(ValueError):
        set_by_path(base_config, _read_only_dotted_params[0], "dummy")


def test_get_params(base_config):
    """
    This test assumes that a configuration is a real nested dictionary.
    This could change in the future, and test should be updated.
    """
    assert get_params("version", config=base_config) == "0.1"
    assert get_params("argo.src", config=base_config) == base_config["argo"]["src"]
    assert len(get_params("argo", config=base_config)) == len(base_config["argo"])
    assert len(get_params("argo.qcflags", config=base_config)) == len(
        base_config["argo"]["qcflags"]
    )


class TestSetParamsSingle:
    """Test cases for the set_params function with different parameter setting approaches for more a single parameter

    This test assumes that a configuration is a real nested dictionary.
    This could change in the future, and test should be updated.
    """

    def assert_this_config(self, config, base_config):
        """Internal to assert a configuration"""

        # Verify the parameters were set correctly
        assert get_params("argo.qcflags.psal", config=config) == [100]

        # Ensure other parameters were not affected
        assert "temp" in config["argo"]["qcflags"]
        assert (
            get_params("argo.qcflags.temp", config=config)
            == base_config["argo"]["qcflags"]["temp"]
        )

    def test_error(self, base_config):
        """Test setting parameters with only a dictionary"""
        config = base_config.copy()

        with pytest.raises(ValueError):
            set_params({"argo.src": "https://..."}, config=config)

    def test_with_keyword_args(self, base_config):
        """Test setting parameters using keyword arguments."""
        config = base_config.copy()

        # Set parameters using keyword arguments
        set_params("argo.qcflags", psal=[100], config=config)

        self.assert_this_config(config, base_config)

    def test_with_dict(self, base_config):
        """Test setting parameters using a dictionary."""
        config = base_config.copy()

        # Set parameters using a dictionary
        set_params("argo.qcflags", {"psal": [100]}, config=config)

        self.assert_this_config(config, base_config)

    def test_with_keyword_args_and_dict(self, base_config):
        """Test setting parameters using a nested dictionary structure."""
        config = base_config.copy()

        # Set parameters using a nested dictionary
        set_params("argo", qcflags={"psal": [100]}, config=config)

        self.assert_this_config(config, base_config)

    def test_with_nested_dict(self, base_config):
        """Test setting parameters using a fully nested dictionary."""
        config = base_config.copy()

        # Set parameters using a fully nested dictionary
        set_params("argo", {"qcflags": {"psal": [100]}}, config=config)

        self.assert_this_config(config, base_config)


class TestSetParamsMultiple:
    """Test cases for the set_params function with different parameter setting approaches for more than one parameter

    This test assumes that a configuration is a real nested dictionary.
    This could change in the future, and test should be updated.
    """

    def assert_this_config(self, config, base_config):
        # Verify the parameters were set correctly
        assert get_params("argo.qcflags.psal", config=config) == [100]
        assert get_params("argo.qcflags.temp", config=config) == [200]

        # Ensure other parameters were not affected
        assert "pres" in config["argo"]["qcflags"]
        assert (
            get_params("argo.qcflags.pres", config=config)
            == base_config["argo"]["qcflags"]["pres"]
        )

    def test_with_keyword_args(self, base_config):
        """Test setting parameters using keyword arguments."""
        config = base_config.copy()

        # Set parameters using keyword arguments
        set_params("argo.qcflags", psal=[100], temp=[200], config=config)

        self.assert_this_config(config, base_config)

    def test_with_dict(self, base_config):
        """Test setting parameters using a dictionary."""
        config = base_config.copy()

        # Set parameters using a dictionary
        set_params("argo.qcflags", {"psal": [100], "temp": [200]}, config=config)

        self.assert_this_config(config, base_config)

    def test_with_keyword_args_and_dict(self, base_config):
        """Test setting parameters using a nested dictionary structure."""
        config = base_config.copy()

        # Set parameters using a nested dictionary
        set_params("argo", qcflags={"psal": [100], "temp": [200]}, config=config)

        self.assert_this_config(config, base_config)

    def test_with_nested_dict(self, base_config):
        """Test setting parameters using a fully nested dictionary."""
        config = base_config.copy()

        # Set parameters using a fully nested dictionary
        set_params("argo", {"qcflags": {"psal": [100], "temp": [200]}}, config=config)

        self.assert_this_config(config, base_config)


class TestResetParams:

    def test_Single(self, base_config):
        """Test reset to one value from reference settings"""

        # Modify the base config:
        x = base_config.copy()
        set_params("name", "Hello World", config=x)

        # Reset back to base config value:
        reset_params("name", config=x, reference=base_config)

        # Check for it:
        assert get_params("name", config=x) == get_params("name", config=base_config)

    def test_All(self, base_config):
        """Test reset to ALL values from reference settings"""
        # Modify the base config:
        x = base_config.copy()
        set_params("name", "Hello World", config=x)
        set_params("argo.src", "http://world", config=x)

        # Reset back ALL PARAMETERS to base config value:
        reset_params(config=x, reference=base_config)

        # Check for it:
        assert get_params("name", config=x) == get_params("name", config=base_config)
        assert get_params("argo.src", config=x) == get_params(
            "argo.src", config=base_config
        )

    def test_Ref_Factory(self, base_config, monkeypatch):
        """Test reset to values from factory settings"""
        x = base_config.copy()
        set_params("name", "My new name", config=x)

        # Define a mocked version of: load_factory_config()
        factory_value = "Reset Name"

        def mock_load_factory_config():
            y = base_config.copy()
            set_params("name", factory_value, config=y)
            return y

        #
        with monkeypatch.context() as m:
            m.setattr(
                do._config.config, "load_factory_config", mock_load_factory_config
            )  # So that reset_params will call the mock
            reset_params(config=x, factory=True)
            assert get_params("name", config=x) == factory_value

    def test_Ref_Default(self, base_config, monkeypatch):
        """Test reset to values from default settings"""
        x = base_config.copy()
        set_params("name", "My new name", config=x)

        # Define a mocked version of: load_configs()
        default_value = "Reset Name"

        def mock_load_configs():
            y = base_config.copy()
            set_params("name", default_value, config=y)
            return y

        #
        with monkeypatch.context() as m:
            m.setattr(
                do._config.config, "load_configs", mock_load_configs
            )  # So that reset_params will call the mock
            reset_params(config=x, factory=False)
            assert get_params("name", config=x) == default_value


def test_config_print_text(base_config, monkeypatch, capfd):
    # With a mock, we do not assume anything about where we're running this test:
    with monkeypatch.context() as m:

        def mock_runner():
            return "terminal"

        m.setattr(
            do._config.config, "runner", mock_runner
        )  # So that config_print will call the mock
        config_print(base_config)
        out, err = capfd.readouterr()
        assert out.startswith("<pydox.configuration>")


@pytest.mark.parametrize(
    "collapsed",
    [True, False],
    indirect=False,
    ids=[f"collapsed={v}" for v in [True, False]],
)
@pytest.mark.parametrize(
    "with_keys",
    [True, False],
    indirect=False,
    ids=[f"with_keys={v}" for v in [True, False]],
)
@pytest.mark.parametrize(
    "tidy", [True, False], indirect=False, ids=[f"tidy={v}" for v in [True, False]]
)
def test_config_print_html(collapsed, with_keys, tidy, base_config, monkeypatch):

    with monkeypatch.context() as m:
        m.setattr(do._config.config, "runner", lambda: "notebook")
        assert isinstance(
            config_print(
                base_config, collapsed=collapsed, with_keys=with_keys, tidy=tidy
            ),
            HTML,
        )


@pytest.mark.skipif(
    True,
    reason="This test is skipped because pydox import argopy that imports cartopy that fails to import even when the system's home directory cannot be accessed.",
)
def test_importable_with_no_home(tmp_path):
    """Test if pydox can be imported even when the system's home directory cannot be accessed.

    We override the pathlib.Path.home method with a lambda function that raises a ZeroDivisionError.
    This effectively breaks the home method, simulating a scenario where the home directory cannot be accessed.

    We also set the PYDOXCONFIGDIR environment variable to a temporary directory provided by the tmp_path fixture.
    This tells Pydox where to look for its configuration files for this edge-case.

    Adapted from Matplotlib:
    https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/tests/test_matplotlib.py#L40
    """
    subprocess_run_for_testing(
        [
            sys.executable,
            "-c",
            "import pathlib; pathlib.Path.home = lambda *args: 1/0; " "import pydox",
        ],
        env={
            **os.environ,
            "MPLCONFIGDIR": str(tmp_path),
            "PYDOXCONFIGDIR": str(tmp_path),
        },
        check=True,
    )
    # todo Re-design this test to handle the cartopy failed import


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
        [sys.executable, "-c", "import pydox; print(pydox.get_configdir())"],
        env={
            **os.environ,
            "LOCALAPPDATA": str(localappdata),
            "USERPROFILE": str(fake_home),
            "PYDOXCONFIGDIR": "",
        },
        capture_output=True,
        text=True,
        check=True,
    )

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
        [sys.executable, "-c", "import pydox; print(pydox.get_configdir())"],
        env={
            **os.environ,
            "LOCALAPPDATA": str(localappdata),
            "USERPROFILE": str(fake_home),
            "PYDOXCONFIGDIR": "",
        },
        capture_output=True,
        text=True,
        check=True,
    )

    configdir = proc.stdout.strip()
    # On Windows with existing old config, should continue using it
    assert configdir == str(old_configdir)


def test_uid(base_config):
    assert uid(base_config) != uid(base_config)


def test_runner(monkeypatch):

    with monkeypatch.context() as m:
        m.setattr(do._config.utils, "get_shell", lambda: "ZMQInteractiveShell")
        assert runner() == "notebook"

    with monkeypatch.context() as m:
        m.setattr(do._config.utils, "get_shell", lambda: "TerminalInteractiveShell")
        assert runner() == "terminal"

    def mock():
        raise NameError()

    with monkeypatch.context() as m:
        m.setattr(do._config.utils, "get_shell", mock)
        assert runner() == "standard"

    with monkeypatch.context() as m:
        m.setattr(do._config.utils, "get_shell", lambda: False)
        assert not runner()


class Dummy:
    def __str__(self):
        return "Dummy"


val_list = ["hello", 12, 1.2, True, [1, 2, 3], Dummy]
val_list_id = [f"{type(v)}" for v in val_list]


@pytest.mark.parametrize("value", val_list, indirect=False, ids=val_list_id)
def test_format_value_txt(value):
    """Test format_value_txt with various input types."""
    assert isinstance(format_value_txt(value), str)


@pytest.mark.parametrize("value", val_list, indirect=False, ids=val_list_id)
def test_format_value_html(value):
    """Test format_value_html with various input types."""
    match = lambda x: re.match(
        r'<span\s+class="[^"]*(?:str|bool|num|list|any)">.*?</span>', x
    )
    assert match(format_value_html(value))
