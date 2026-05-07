from typing import Any, Optional
import logging
from pathlib import Path

import numpy as np

from pydox.io.argo.types import ArgoDataForInAir


log = logging.getLogger("pydox.io.ncep.facade")


def get_ncep_data_for_in_air_method(
    argo_data: ArgoDataForInAir,
    src: str | Path,
    name: Optional[str] = None,
    debug_plot: bool = False,
) -> dict[str, Any]:
    """

    Parameters
    ----------
    argo_data: ArgoDataForInAir
        A dataclass as output from the :func:`do.calibration.methods.in_air.utils.get_argo_data_for_in_air_method` function.
    name: Optional[str]
        NCEP nickname to use.
    src: str | Path
        Source of the NCEP dataset. This can be a string or a :class:`Path` object.
    debug_plot: bool = False

    Returns
    -------
    dict[str, Any]
    """
    name: str = "NCEP" if name is None else name

    # Init output obj:
    data: dict[str, Any] = {"REF_PPOX": None}

    # todo Implement real NCEP data loading here
    # open_ncep()
    # interp_ncep(argo_data)
    # compute_ncep_ppox()

    # Create dummy data:
    data["REF_PPOX"] = np.random.random_sample(
        (len(argo_data.in_air["PPOX_DOXY"].values),)
    )
    log.info(f"Return dummy data for {name}, based on {src}")

    #
    return data
