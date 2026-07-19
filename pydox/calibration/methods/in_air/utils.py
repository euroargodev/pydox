from typing import Any, Optional
import logging

import argopy as ar
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt

import pydox as do
from pydox._config.config import Config
from pydox.commodities import ParameterSet, ParamsInAir, TPlotParams, PlotParams
from pydox.reporting.utils import fig_commit
from pydox.io.argo.types import ArgoDataForInAir

from pydox.io.argo.facade import get_argo_data_for_in_air_method, semantic_cycle2values
from pydox.io.ncep.facade import get_ncep_data_for_in_air_method


log = logging.getLogger("pydox.calibration.methods.in_air.utils")


def get_argo_data(
    a_float: ar.ArgoFloat,
    config: Config,
    params: Optional[ParameterSet] = None,
    uid: Optional[str] = None,
    ppar: Optional[TPlotParams] = None,
) -> ArgoDataForInAir | dict[str, xr.Dataset]:
    """Load Argo float data to correct oxygen with atmospheric data (in-air method)"""
    print(f"Load Argo data ({a_float.WMO})")

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
    cycles: tuple[int] = semantic_cycle2values(
        a_float=a_float, settings=config if params is None else params
    )

    # Call low-level/internal function:
    data: ArgoDataForInAir = get_argo_data_for_in_air_method(
        min_pres=min_pres,
        max_pres=max_pres,
        in_air_codes=in_air_codes,
        in_water_codes=in_water_codes,
        which_psal=which_psal,
        cycles=cycles,
        Sprof=Sprof,
        Rtraj=Rtraj,
        uid=uid,
        ppar=ppar,
    )
    data.optode_height = optode_height
    data.launch_date = a_float.dataset("meta")["LAUNCH_DATE"].values

    return data


def get_atmospheric_data(
    argo_data: ArgoDataForInAir,
    config: Config,
    # params: Optional[ParamsInAir] = None,
    uid: Optional[str] = None,
    ppar: Optional[TPlotParams] = None,
) -> dict[str, Any]:
    """Load reference data to correct oxygen with atmospheric data (in-air method)"""
    dataset: str = do.get_params("calibration_methods.in_air.dataset", config=config)
    print(f"Load atmospheric data ({dataset})")

    if dataset == "ncep":
        # name: str = do.get_params(
        #     "calibration_methods.in_air.data.ncep.name", config=config
        # )
        #
        # if params is None:
        #     src: str = do.get_params(
        #         "calibration_methods.in_air.data.ncep.src", config=config
        #     )
        # else:
        #     src: str = params.src

        data = get_ncep_data_for_in_air_method(argo_data, uid=uid, ppar=ppar)
    else:
        raise NotImplementedError(
            f"No implementation to load the atmospheric dataset={dataset}"
        )

    return data


def get_data_for_one_parameterset_for_in_air_method(
    a_float: ar.ArgoFloat,
    config: Config,
    params: ParamsInAir,
    iset: Optional[int] = None,
    uid: Optional[str] = None,
    ppar: Optional[TPlotParams] = None,
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
    uid: str, optional, default=None
        Unique string identifier of the caller object. This is used for reports, to track the configuration set calling this function.
    ppar: optional, default=None
        Plot parameters

    Returns
    -------
    data | [data, iset]
    """
    # Get plotting parameters:
    # Expected use-case: ppar is a partial of PlotParams inherited from high-level calibration methods.
    # Otherwise, with a direct call to this method:
    # - note that the below kwargs `uid` and `level` are used only if ppar is None,
    # - the below kwargs `level` is set to 1 because this is the expected plotting level for input data related plots.
    ppar: PlotParams = PlotParams.from_obj(ppar, uid=uid, level=1)
    ppar.uid = (
        uid if uid is not None else ppar.uid
    )  # Ensure to use the last possible uid value

    data: dict[str, Any] = {
        "PPOX1": None,
        "PPOX2": None,
        "REF_PPOX": None,
        "CYCLE_NUMBER": None,
        "Delta_T_REF": None,
    }  # Collect obj for output
    # todo Consider using a dataclass instead of a dictionary

    # Load Argo float data:
    this_argo = get_argo_data(a_float, config, params, uid=uid, ppar=ppar)
    data["PPOX1"]: np.ndarray = this_argo.in_air["PPOX_DOXY"].values
    data["PPOX2"]: np.ndarray = this_argo.in_water["PPOX_DOXY"].values
    data["CYCLE_NUMBER"]: list[int] = [
        int(v) for v in this_argo.in_air["CYCLE_NUMBER"].values
    ]
    data["Delta_T_REF"]: np.ndarray = (
        this_argo.in_air["JULD"].values - this_argo.launch_date
    ) / np.timedelta64(1, "D")

    # Load Atmospheric data:
    this_atm = get_atmospheric_data(this_argo, config, uid=uid, ppar=ppar)
    data["REF_PPOX"]: np.ndarray = this_atm["REF_PPOX"]

    if ppar.level <= 1:
        refname = do.get_params("calibration_methods.in_air.dataset", config=config)
        title = "Partial pressure of oxygen (PPOX) used for fitting"

        fig, ax = plt.subplots(
            nrows=1,
            ncols=1,
            figsize=(10, 4),
            dpi=ppar.dpi,
            sharex=True,
        )
        ax.plot(
            this_argo.in_air["CYCLE_NUMBER"], data["PPOX1"], ".-r", label="Float In-Air"
        )
        ax.plot(
            this_argo.in_water["CYCLE_NUMBER"],
            data["PPOX2"],
            ".-b",
            label="Float In-Water",
        )
        ax.plot(
            this_argo.in_air["CYCLE_NUMBER"],
            data["REF_PPOX"],
            ".-k",
            label=f"Ref-{refname}",
        )
        ax.grid()
        ax.set_xlabel("Float cycle number of the measurement")
        ax.set_ylabel("[mb]")
        ax.set_title(title)
        ax.legend()
        plt.tight_layout()
        fig_commit(
            fig,
            name=title,
            watermark=ppar.watermark,
            category="input_data",
            config_uid=ppar.uid,
        )

    if ppar.level <= 1:
        refname = do.get_params("calibration_methods.in_air.dataset", config=config)
        title = f"Ratio of 'Ref-{refname}' vs 'In-Air' partial pressure of oxygen"

        fig, ax = plt.subplots(
            nrows=1,
            ncols=1,
            figsize=(10, 4),
            dpi=ppar.dpi,
            sharex=True,
        )
        ax.plot(data["Delta_T_REF"], data["REF_PPOX"] / data["PPOX1"], ".-")

        ax.set_xlabel("Delta Time [Days]")
        ax.set_ylabel("[no unit]")
        ax.grid()
        mask = np.isfinite(data["REF_PPOX"]) & np.isfinite(data["PPOX1"])
        poly_data = np.polyfit(
            data["Delta_T_REF"][mask], data["REF_PPOX"][mask] / data["PPOX1"][mask], 1
        )
        ax.plot(
            data["Delta_T_REF"],
            np.polyval(poly_data, data["Delta_T_REF"]),
            "-r",
            label="Linear fit",
        )
        ax.set_title(title)
        fig_commit(
            fig,
            name=title,
            watermark=ppar.watermark,
            category="input_data",
            config_uid=ppar.uid,
        )

    # Return
    if iset is None:
        return data
    else:
        return data, iset
