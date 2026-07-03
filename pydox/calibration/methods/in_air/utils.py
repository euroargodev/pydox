from typing import Any, Optional
import logging

import argopy as ar
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParameterSet, ParamsInAir
from pydox.reporting.utils import fig_commit
from pydox.io.argo.types import ArgoDataForInAir

from pydox.io.argo.facade import get_argo_data_for_in_air_method, semantic_cycle2values
from pydox.io.ncep.facade import get_ncep_data_for_in_air_method


log = logging.getLogger("pydox.calibration.methods.in_air.utils")


# class ArgoData:
#
#     def __init__(self, wmo: int, **kwargs) -> None:
#         self._cfg: Config = deepcopy(kwargs.get("config", do.params))
#         self.a_float: ar.ArgoFloat = ar.ArgoFloat(
#             wmo, host=do.get_params("argo.src", config=self._cfg), cache=True
#         )
#         self.cast = kwargs.get("cast", True)
#         self._sprof = None
#         self._rtraj = None
#
#     @property
#     def Sprof(self) -> xr.Dataset:
#         if self._sprof is None:
#             self._sprof = self.a_float.open_dataset("Sprof", cast=self.cast)
#         return self._sprof
#
#     @property
#     def Rtraj(self) -> xr.Dataset:
#         if self._rtraj is None:
#             self._rtraj = self.a_float.open_dataset("Rtraj", cast=self.cast)
#         return self._rtraj


def get_argo_data(
    a_float: ar.ArgoFloat,
    config: Config,
    params: Optional[ParameterSet] = None,
    debug_plot: bool = False,
) -> ArgoDataForInAir | dict[str, xr.Dataset]:
    """Load Argo float data to correct oxygen with atmospheric data (in-air method)"""

    # Read parameters from the configuration object:
    optode_height = do.get_params("argo.optode_height", config=config)
    if "CONFIG_OptodeVerticalPressureOffset_dbar" in a_float.launchconfig.parameters:
        optode_height = a_float.launchconfig["OptodeVerticalPressureOffset_dbar"]

    min_pres: float = do.get_params(
        "argo.in_water_salinity.min_pressure", config=config
    )
    max_pres: float = do.get_params(
        "argo.in_water_salinity.max_pressure", config=config
    )
    in_air_codes: tuple[int] = do.get_params("argo.codes.in_air", config=config)
    in_water_codes: tuple[int] = do.get_params("argo.codes.in_water", config=config)
    which_psal: int = do.get_params("argo.use", config=config)

    # Pre-load Argo data
    # (we also check that the ArgoFloat instance is indeed using the same Argo data source as the configuration)
    src = do.get_params("argo.src", config=config)
    src = ar.utils.lists.shortcut2gdac(src)
    if src != a_float.host:
        raise ValueError(
            f"You are trying to load Argo data with an ArgoFloat instance that is not pointing to the same GDAC ('{a_float.host}') as the current Pydox configuration  ('{src}').\nYou must provide an ArgoFloat instance with the appropriate 'host' argument, eg: ArgoFloat(host=do.get_params('argo.src'))."
        )

    # GDAC Argo data are loaded from file (local or remote) when accessing 'Sprof' and 'Rtraj' from the ArgoFloat dataset method:
    Sprof: xr.Dataset = a_float.dataset("Sprof")
    Rtraj: xr.Dataset = a_float.dataset("Rtraj")

    # Read other parameters from the ParameterSet object:
    cycles: tuple[int] = tuple(
        semantic_cycle2values(
            a_float=a_float, settings=config if params is None else params
        )
    )

    # Call low-level/internal function:
    data = get_argo_data_for_in_air_method(
        min_pres=min_pres,
        max_pres=max_pres,
        in_air_codes=in_air_codes,
        in_water_codes=in_water_codes,
        which_psal=which_psal,
        cycles=cycles,
        Sprof=Sprof,
        Rtraj=Rtraj,
        debug_plot=debug_plot,
    )
    data.optode_height = optode_height
    data.launch_date = a_float.dataset("meta")["LAUNCH_DATE"].values

    return data


def get_atmospheric_data(
    argo_data: ArgoDataForInAir,
    config: Config,
    params: Optional[ParamsInAir] = None,
    debug_plot: bool = False,
) -> dict[str, Any]:
    """Load reference data to correct oxygen with atmospheric data (in-air method)"""

    dataset: str = do.get_params("calibration_methods.in_air.dataset", config=config)

    if dataset == "ncep":
        name: str = do.get_params(
            "calibration_methods.in_air.data.ncep.name", config=config
        )

        if params is None:
            src: str = do.get_params(
                "calibration_methods.in_air.data.ncep.src", config=config
            )
        else:
            src: str = params.src

        data = get_ncep_data_for_in_air_method(
            argo_data, name=name, debug_plot=debug_plot
        )
    else:
        raise NotImplementedError(f"No implementation to load dataset={dataset}")

    return data


def get_data_for_one_parameterset_for_in_air_method(
    a_float: ar.ArgoFloat,
    config: Config,
    params: ParamsInAir,
    iset: Optional[int] = None,
    debug_plot: bool = False,
    uid: str = "",
) -> dict[str, Any] | tuple[dict[str, Any], int]:
    """Load and process all data (Argo and atmosphere) required for a single fit

    All downstream methods should rely on values from the `params` argument first, and then on values from `config`.
    We use both because some settings may not be available in `params` attributes (this is not satisfactory and should change in the future).

    Parameters
    ----------
    a_float: ar.ArgoFloat
    config: Config
    params: ParamsInAir
    iset: int, optional, default=None
        Untouched, this argument is simply return to keep track of this configuration set in the procedure when performed in parallel.
    debug_plot: bool, optional, default=False
    uid: str, default = ""
        Unique string identifier of the caller object. This is used for reporting to track who's calling this function and with which configuration.

    Returns
    -------
    iset, data
    """
    data: dict[str, Any] = {
        "PPOX1": None,
        "PPOX2": None,
        "REF_PPOX": None,
        "CYCLE_NUMBER": None,
        "Delta_T_REF": None,
    }  # Collect obj for output
    # todo Consider using a dataclass instead of a dictionary

    # Load Argo float data:
    this_argo = get_argo_data(a_float, config, params, debug_plot=debug_plot)
    data["PPOX1"]: np.ndarray = this_argo.in_air["PPOX_DOXY"].values
    data["PPOX2"]: np.ndarray = this_argo.in_water["PPOX_DOXY"].values
    data["CYCLE_NUMBER"]: list[int] = [
        int(v) for v in this_argo.in_air["CYCLE_NUMBER"].values
    ]
    data["Delta_T_REF"]: np.ndarray = (
        this_argo.in_air["JULD"] - this_argo.launch_date
    ) / np.timedelta64(1, "D")

    # Load Atmospheric data:
    this_atm = get_atmospheric_data(this_argo, config, params, debug_plot=debug_plot)
    data["REF_PPOX"]: np.ndarray = this_atm["REF_PPOX"]

    if debug_plot:
        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 4), dpi=90, sharex=True)
        title = "PPOX (Partial pressure of oxygen) used for fitting"
        ax.plot(this_argo.in_air["CYCLE_NUMBER"], data["PPOX1"], ".-b", label="InAir")
        ax.plot(
            this_argo.in_water["CYCLE_NUMBER"], data["PPOX2"], ".-r", label="InWater"
        )
        ax.plot(this_argo.in_air["CYCLE_NUMBER"], data["REF_PPOX"], ".-k", label="Ref")
        ax.grid()
        ax.set_xlabel("Float cycle number of the measurement")
        ax.set_ylabel("[mb]")
        ax.set_title(title)
        plt.legend()
        plt.tight_layout()
        plt.show()
        fig_commit(fig, name=title, caller_uid=uid)

        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 4), dpi=90, sharex=True)
        title = "Ratio of 'Ref' vs 'InWater' partial pressure of oxygen"
        ax.plot(data["Delta_T_REF"], data["REF_PPOX"] / data["PPOX1"], ".-")
        ax.set_xlabel("Delta Time (Days)")
        ax.set_ylabel("REFERENCE_DATA/INAIR_ARGO_DATA [no unit]")
        ax.grid()
        mask = np.isfinite(data["REF_PPOX"]) & np.isfinite(data["PPOX1"])
        poly_data = np.polyfit(
            data["Delta_T_REF"][mask], data["REF_PPOX"][mask] / data["PPOX1"][mask], 1
        )
        ax.plot(data["Delta_T_REF"], np.polyval(poly_data, data["Delta_T_REF"]), "*-r")
        ax.set_title(title)
        plt.show()
        fig_commit(fig, name=title, caller_uid=uid)

    # Return
    if iset is None:
        return data
    else:
        return data, iset
