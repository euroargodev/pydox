from typing import Optional, Any
from pathlib import Path
import matplotlib

import pydox as do
from pydox._config.config import _path2static
from pydox.reporting.colors import ColorScheme
from pydox.reporting.logs import getLogger

log = getLogger("reporting.facade", 20)


def mpl_style_use(config: Optional[Any] = None) -> None:
    """Load and set Matplotlib to use stylesheet from a configuration

    If any, load and set Matplotlib to use the stylesheet from the configuration setting: "reports.plots.mplstyle".

    If the stylesheet uses shortnames like "{COLOR.DARK}" or "{COLOR.LIGHTEST}" for colors, they are automatically replaced with real RGBA values based on the "reports.templates.<reports.template>.colors" configuration setting.

    Parameters
    ----------
    config

    Returns
    -------
    None
    """
    mplstyle_file = _path2static.joinpath("mplstyle")
    if do.get_params("plots.mplstyle", config=config) is not None:
        mplstyle_file = Path(do.get_params("plots.mplstyle", config=config))

    # Load Matplotlib stylesheet and:
    # - remove comments
    # - replace template color shortnames with their real values, eg: "{COLOR.DARK}" is replaced with
    mplstyle = {}
    with open(mplstyle_file, "r") as f:
        lines = f.readlines()
    for line in lines:
        if ":" in line and not line.startswith("#"):
            key = line.split(":")[0]
            val = line[line.index(":") + 1 :].strip()
            for color in do.reporting.COLORS._KEYS:
                val = val.replace(
                    f"{'{'}COLORS.{color}{'}'}",
                    f"{getattr(do.reporting.COLORS, color)}",
                )
            mplstyle[key] = val.split("#")[0].strip()

    matplotlib.pyplot.style.use(mplstyle)


def load_template(config: Optional[Any] = None) -> None:
    """Load template (color scheme, Matplotlib stylesheet, etc...)

    This function does the following:
    - Set :class:`pydox.reporting.COLORS` with the template color scheme define with the configuration setting: "reports.templates.<reports.template>.colors".
    - If any, load and set Matplotlib to use the stylesheet from the configuration setting: "reports.templates.<reports.template>.mplstyle".

    Parameters
    ----------
    config

    Returns
    -------
    None

    See Also
    --------
    :func:`pydox.reporting.facade.mpl_style_use`
    """
    do.reporting.COLORS = ColorScheme.from_config(config)
    mpl_style_use(config)
