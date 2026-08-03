from typing import Optional
from pathlib import Path
import matplotlib

import pydox as do
from pydox._config.config import _path2static
from pydox.reporting.colors import Template2Colors
from pydox.reporting.logs import getLogger

log = getLogger("reporting.facade", 20)


def load_template():
    do.reporting.COLORS = Template2Colors.from_config(do.params)

    if do.get_params("reports.template.mplstyle") is not None:
        mplstyle_file = Path(do.get_params("reports.template.mplstyle"))
    else:
        mplstyle_file = _path2static.joinpath("mplstyle")

    # Apply template color scheme to the mpl style file:
    mplstyle = {}
    with open(mplstyle_file, "r") as f:
        lines = f.readlines()
    for line in lines:
        if not line.startswith("#"):
            print(line)
            for color in [
                "DARKEST",
                "DARK",
                "MEDIUM_DARK",
                "MEDIUM",
                "LIGHT_MEDIUM",
                "LIGHT",
                "LIGHTEST",
            ]:
                line = line.replace(
                    f"COLORS.{color}", f"{getattr(do.reporting.COLORS, color)}"
                )
            mplstyle[line.split(":")[0]] = line.split(":")[-1]
    log.info(mplstyle)

    matplotlib.pyplot.style.use(mplstyle)

    pass
