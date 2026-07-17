from pathlib import Path

# import uuid
import datetime

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
from pydox.commodities import PydoxFigure

#
from importlib.metadata import version as _version

try:
    __version__ = _version("pydox")
except Exception:
    # Local copy or not installed with setuptools.
    # Disable minimum version checks on downstream libraries.
    __version__ = "9999"

# Define module level placeholder for the list of figure objects:
__figures: list[PydoxFigure] = []

# Auto-creation of output folders:
root = Path(get_params("output.root"))
root.mkdir(parents=True, exist_ok=True)

# tmp_root = root.joinpath("tmp").joinpath(uuid.uuid4().hex)
tmp_root = root.joinpath("tmp").joinpath(
    datetime.datetime.now(datetime.timezone.utc).strftime("%d%m%y%H%M%S%f")
)
tmp_root.mkdir(parents=True, exist_ok=True)
print(tmp_root)
