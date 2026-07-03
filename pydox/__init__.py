from pathlib import Path

# Import facades for configuration management:
from pydox._config.config import (
    get_params,
    set_params,
    reset_params,
    config_files,
    config_print,
    get_configdir,
)
from pydox._config.config import rcParams as params

from pydox.calibration.facade import Calibration, CalibrationSet
from pydox.commodities import Figure

#
from importlib.metadata import version as _version

try:
    __version__ = _version("pydox")
except Exception:
    # Local copy or not installed with setuptools.
    # Disable minimum version checks on downstream libraries.
    __version__ = "9999"

# Define module level placeholder for figures
__figures: list[Figure] = []

root = Path(get_params("output.root"))
root.mkdir(parents=True, exist_ok=True)
tmp_root = root.joinpath("tmp")
tmp_root.mkdir(parents=True, exist_ok=True)
