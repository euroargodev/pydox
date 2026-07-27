from pathlib import Path
import pickle
from typing import Optional, List
from collections import OrderedDict
import matplotlib as mpl

import pydox as do
from pydox.commodities import PydoxFigure


def fig_commit(
    fig: mpl.figure.Figure,
    name: str,
    category: Optional[str] = None,
    watermark: Optional[str] = None,
    dest: Optional[Path] = None,
    config_uid: Optional[str] = None,
):
    """Commit a named :mpl:`Figure` object to the global registry of figures

    The :mpl:`Figure` object is automatically pickled (in a tmp folder) for later re-open or re-use in the session.
    The :mpl:`Figure` object is also closed upon commit.
    """
    if name.strip() == "" or name is None:
        raise ValueError("A figure must have a name to be commited")

    new_f = PydoxFigure(fig=fig, name=name, category=category, config_uid=config_uid)

    found = False
    for f in do.__figures:
        if new_f.uid == f.uid:
            found = True

    if not found:
        print(f"Commit figure ({new_f.category} - '{new_f.name}')")

        # Add watermark:
        default_watermark = do.get_params("plots.watermark")
        show_watermark = watermark is not None or default_watermark is not None

        if show_watermark:
            if default_watermark is not None:
                if watermark is None:
                    watermark = default_watermark
                else:
                    watermark = "\n".join([watermark, default_watermark])

            for ax in fig.axes:
                ax.text(
                    0.5,
                    0.5,
                    watermark,
                    transform=ax.transAxes,
                    fontsize=40,
                    color="gray",
                    alpha=0.5,
                    ha="center",
                    va="center",
                    rotation=30,
                )

        # Save figure object to a pickle file:
        dest = do.tmp_root() if dest is None else Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        pkl = dest.joinpath(f"{new_f.uid}.pkl")
        with open(pkl, "wb") as fid:
            pickle.dump(new_f.fig, fid)

        # Add to internal global registry:
        new_f.pickle = pkl
        do.__figures.append(new_f)

        # Close figure upon commit
        # (.show() is controlled by higher-level methods .plot() methods)
        mpl.pyplot.close(fig)


def method_figure_list(obj) -> List[PydoxFigure]:
    results: List[PydoxFigure] = []
    for f in do.__figures:
        if f.config_uid is not None and f.config_uid.startswith(obj.uid()):
            results.append(f)
    return results


def configs_figure_list(obj) -> OrderedDict[int, List[PydoxFigure]]:
    """Create a dictionary of figures for a given object with a `configs` attribute of type ConfigsDict"""
    results = OrderedDict()
    for iset, params in obj.configs.items():
        results[iset]: List[PydoxFigure] = []
        for f in do.__figures:
            if f.config_uid is not None and f.config_uid.startswith(obj.uid(iset)):
                results[iset].append(f)
    return results
