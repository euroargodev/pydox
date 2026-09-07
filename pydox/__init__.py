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
from pydox._config.utils import tmp_root

from pydox.calibration.facade import Calibration, CalibrationSet
from pydox.reporting.facade import load_template

import matplotlib
from importlib.metadata import version as _version

try:
    __version__ = _version("pydox")
except Exception:
    # Local copy or not installed with setuptools.
    # Disable minimum version checks on downstream libraries.
    __version__ = "9999"

# Define global figure registry and manager:
from pydox.commodities import PydoxFigure, _DoFigures

__figures: list[PydoxFigure] = []  # Internal global registry of figures
figures = _DoFigures(__figures)  # Facade for the registry manager of figures

# Load and apply default template:
load_template()
