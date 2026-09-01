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

# Import facades for calibrations:
from pydox.calibration.facade import Calibration, CalibrationSet

#
from importlib.metadata import version as _version

try:
    __version__ = _version("pydox")
except Exception:
    # Local copy or not installed with setuptools.
    # Disable minimum version checks on downstream libraries.
    __version__ = "9999"
