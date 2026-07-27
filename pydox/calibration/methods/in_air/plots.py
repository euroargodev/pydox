from typing import Dict, Any, Optional
import numpy as np
import matplotlib.pyplot as plt

import pydox as do
from pydox.commodities import (
    CoefsDict,
    TPlotParams,
    PlotParams,
    CoefficientsInAir,
)
from pydox.reporting.utils import fig_commit

# A function to return True if 2 numpy arrays have similar values, ignoring NaNs, but ensuring they are located at the same index:
array_equal = (
    lambda x, y: np.equal(np.isnan(x), np.isnan(y)).all()
    and np.equal(x[~np.isnan(x)], y[~np.isnan(x)]).all()
)


def data_equal(data, param):
    """Return True if all arrays of a parameters from a dict of dict are similar

    This is to be used with dict `input_data` that has configuration numbers as keys.

    Parameters
    ----------
    data: Dict[int, Dict[param: str, np.array]]
    param: str
        Some key in the sub dict
    """
    if np.unique([len(data[ii][param]) for ii in range(len(data))]).size > 1:
        return False
    else:
        return np.all(
            [array_equal(data[0][param], data[ii][param]) for ii in range(len(data))]
        )


def predict(coefs: CoefficientsInAir, data: dict[int, Any]) -> Any:
    """Predict adjusted values

    Parameters
    ----------
    coefs: CoefficientsInAir
        Adjustment coefficients object (gain, drift, ...).
        This is typically one value from the :attr:`Calibration.coefs` property.
    data: dict[int, Any]
        The data obj is defined in :func:`pydox.calibration.methods.in_air.utils.get_data_for_one_parameterset_for_in_air_method`.
        This is typically one value from the :attr:`Calibration.input_data` property.

    Returns
    -------
    Any
        But most likely a :class:`np.ndarray`
    """
    ydata = data["PPOX1"] * coefs.gain.value
    if coefs.drift is not None:
        # Apply drift if necessary
        ydata = ydata * (1 + coefs.drift.value / 100 * data["Delta_T_REF"] / 365)
    return ydata


def plot_fit_results_hue(
    input_data: Dict[int, Any],
    coefs: CoefsDict,
    uid: str = "",
    ppar: Optional[TPlotParams] = None,
) -> None:
    """Plot in-air fit results, each config superimposed on a single plot

    Input Ref and Argo in-air are only plotted once if data are similar for all configurations.

    Parameters
    ----------
    input_data: Dict[int, Any]
    coefs: CoefsDict
    uid: str = ""
    ppar: Optional[TPlotParams] = None
    """
    _this_plot_level = 2

    if ppar is None:
        ppar = PlotParams(
            dpi=do.get_params("plots.dpi"),
            level=do.get_params("plots.level"),
        )
    if ppar.level > _this_plot_level:
        print(
            f"This plot was not generated because plots.level {ppar.level} is higher than this plot level {_this_plot_level}"
        )
        return None

    suptitle = "Calibration results"
    ylabel = "Partial pressure of oxygen [mb]"

    fig, ax = plt.subplots(
        nrows=1,
        ncols=1,
        figsize=(10, 6),
        dpi=ppar.dpi,
    )

    for iset in range(len(input_data)):
        xdata = input_data[iset]["CYCLE_NUMBER"]
        xlabel = "Float Cycle number of the measurement"

        if (
            data_equal(input_data, "REF_PPOX")
            and "Ref" not in ax.get_legend_handles_labels()[-1]
        ):
            # Plot REF_PPOX only once
            ax.plot(
                xdata,
                input_data[iset]["REF_PPOX"],
                ".-",
                label="Ref",
            )
        elif not data_equal(input_data, "REF_PPOX"):
            # Unless it is not the same for all input data
            ax.plot(
                xdata,
                input_data[iset]["REF_PPOX"],
                ".-",
                label=f"Ref (config {iset})",
            )

        if (
            data_equal(input_data, "PPOX1")
            and "Non-adjusted (in-air)" not in ax.get_legend_handles_labels()[-1]
        ):
            # Plot non-adjusted in-air oxygen data only once
            ax.plot(
                xdata,
                input_data[iset]["PPOX1"],
                ".-",
                label="Non-adjusted (in-air)",
            )
        elif not data_equal(input_data, "PPOX1"):
            # Unless it is not the same for all input data
            ax.plot(
                xdata,
                input_data[iset]["PPOX1"],
                ".-",
                label=f"Non-adjusted (in-air) (config {iset})",
            )

        # Plot in-air oxygen adjusted values
        ydata = predict(coefs[iset], input_data[iset])
        ax.plot(
            xdata,
            ydata,
            ".-",
            label=f"Adjusted (config {iset})",
        )

    ax.grid()
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.set_title(suptitle)

    fig_commit(
        fig,
        name=f"{suptitle} [configs_layout='hue']",
        category="fit_results",
        watermark=ppar.watermark,
        config_uid=uid,
    )


def plot_fit_results_subplot(
    input_data: Dict[int, Any],
    coefs: CoefsDict,
    uid: str = "",
    ppar: Optional[TPlotParams] = None,
    figsize=(10, 5),
) -> None:
    """Plot in-air fit results, one subplot for each config result (n_configs rows, 1 column)"""
    _this_plot_level = 2

    if ppar is None:
        ppar = PlotParams(
            dpi=do.get_params("plots.dpi"),
            level=do.get_params("plots.level"),
        )
    if ppar.level > _this_plot_level:
        print(
            f"This plot was not generated because plots.level {ppar.level} is higher than this plot level {_this_plot_level}"
        )
        return None

    suptitle = "Calibration results"
    ylabel = "Partial pressure of oxygen [mb]"

    fig, ax = plt.subplots(
        nrows=len(input_data),
        ncols=1,
        figsize=figsize,
        dpi=ppar.dpi,
        sharex=True,
    )
    ax = ax.flatten() if isinstance(ax, np.ndarray) else np.array(ax)[np.newaxis]

    for iset in range(len(input_data)):
        xdata = input_data[iset]["CYCLE_NUMBER"]
        xlabel = "Float Cycle number of the measurement"

        # Plot the reference:
        ax[iset].plot(xdata, input_data[iset]["REF_PPOX"], ".-", label="Ref")

        # Plot the input non-adjusted value:
        ax[iset].plot(
            xdata,
            input_data[iset]["PPOX1"],
            ".-",
            label="Non-adjusted (in-air)",
        )

        # Plot the adjusted value:
        ydata = predict(coefs[iset], input_data[iset])
        ax[iset].plot(
            xdata,
            ydata,
            ".-",
            label=f"Adjusted (config {iset})",
        )

        ax[iset].grid()
        ax[iset].set_xlabel(xlabel)
        ax[iset].set_ylabel(ylabel)
        ax[iset].legend()
        ax[iset].set_title(f"Correction : {iset}")

    # plt.tight_layout()
    plt.suptitle(suptitle)

    fig_commit(
        fig,
        name=f"{suptitle} [configs_layout='subplot']",
        category="fit_results",
        watermark=ppar.watermark,
        config_uid=uid,
    )
