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
from pydox.calibration.methods.in_air.utils import data_equal


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
    ppar: Optional[TPlotParams] = None,
    figsize=(10, 4),
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
    this_plot_level = 20

    ppar: PlotParams = PlotParams.get(ppar)
    if this_plot_level < ppar.level:
        print(
            f"This plot was not generated because plots.level {ppar.level} is higher than this plot level {this_plot_level}"
        )
        return None

    suptitle = "Calibration results"
    ylabel = "Partial pressure of oxygen [mb]"

    fig, ax = plt.subplots(
        nrows=1,
        ncols=1,
        figsize=figsize,
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

    ax.grid(True)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    ax.set_title(suptitle)

    do.figures.commit(
        fig,
        name=f"{suptitle} [configs_layout='hue']",
        category="fit_results",
        watermark=ppar.watermark,
        config_uid=ppar.uid,
    )


def plot_fit_results_subplot(
    input_data: Dict[int, Any],
    coefs: CoefsDict,
    ppar: Optional[TPlotParams] = None,
    # figsize=(10, 4),
) -> None:
    """Plot in-air fit results, one subplot for each config result (n_configs rows, 1 column)"""
    this_plot_level = 20

    ppar = PlotParams.get(ppar)
    if this_plot_level < ppar.level:
        print(
            f"This plot was not generated because plots.level {ppar.level} is higher than this plot level {this_plot_level}"
        )
        return None

    suptitle = "Calibration results"
    ylabel = "Partial pressure of oxygen [mb]"

    fig, ax = plt.subplots(
        nrows=len(input_data),
        ncols=1,
        figsize=(10, 4 * len(input_data)),
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

        ax[iset].grid(True)
        ax[iset].set_xlabel(xlabel)
        ax[iset].set_ylabel(ylabel)
        ax[iset].legend()
        ax[iset].set_title(f"Correction : {iset}")

    # plt.tight_layout()
    plt.suptitle(suptitle)

    do.figures.commit(
        fig,
        name=f"{suptitle} [configs_layout='subplot']",
        category="fit_results",
        watermark=ppar.watermark,
        config_uid=ppar.uid,
    )


def plot_fit_results_figure(
    input_data: Dict[int, Any],
    coefs: CoefsDict,
    ppar: Optional[TPlotParams] = None,
    figsize=(10, 4),
) -> None:
    """Plot in-air fit results, one figure for each config result"""
    this_plot_level = 20

    ppar = PlotParams.get(ppar)
    if this_plot_level < ppar.level:
        print(
            f"This plot was not generated because plots.level {ppar.level} is higher than this plot level {this_plot_level}"
        )
        return None

    suptitle = "Calibration results"
    ylabel = "Partial pressure of oxygen [mb]"

    for iset in range(len(input_data)):
        fig, ax = plt.subplots(
            nrows=1,
            ncols=1,
            figsize=figsize,
            dpi=ppar.dpi,
        )
        ax = ax.flatten() if isinstance(ax, np.ndarray) else np.array(ax)[np.newaxis]

        xdata = input_data[iset]["CYCLE_NUMBER"]
        xlabel = "Float Cycle number of the measurement"

        # Plot the reference:
        ax[0].plot(xdata, input_data[iset]["REF_PPOX"], ".-", label="Ref")

        # Plot the input non-adjusted value:
        ax[0].plot(
            xdata,
            input_data[iset]["PPOX1"],
            ".-",
            label="Non-adjusted (in-air)",
        )

        # Plot the adjusted value:
        ydata = predict(coefs[iset], input_data[iset])
        ax[0].plot(
            xdata,
            ydata,
            ".-",
            label=f"Adjusted (config {iset})",
        )

        ax[0].grid(True)
        ax[0].set_xlabel(xlabel)
        ax[0].set_ylabel(ylabel)
        ax[0].legend()
        ax[0].set_title(f"Calibration results for correction : {iset}")

        # plt.tight_layout()

        do.figures.commit(
            fig,
            name=f"{suptitle} [configs_layout='figure', iset='{iset}']",
            category="fit_results",
            watermark=ppar.watermark,
            config_uid=ppar.uid,
        )
