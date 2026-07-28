from pathlib import Path
import pickle
from typing import Optional
import matplotlib as mpl

import pydox as do
from pydox.commodities import PydoxFigure


def fig_commit(
    fig: mpl.figure.Figure,
    name: str,
    category: Optional[str] = None,
    watermark: Optional[str] = None,
    config_uid: Optional[str] = None,
    dest: Optional[Path] = None,
):
    """Commit a named :mpl:`Figure` object to the global registry of figures

    This function is to be called from anywhere in the library.

    A commit is the following set of operations:
    - create a new :class:`do.PydoxFigure` instance and append it to the global registry if not already there,
    - print a watermark on each axes of the figure (if `plots.watermark.show` is set to True),
    - save the :mpl:`Figure` object on a temporary pickle file,
    - close the :mpl:`Figure` object (show or save is managed elsewhere using the global registry).

    Use the registry to report/show figures matching some criteria based on meta-data filtering.

    Parameters
    ----------
    fig: :class:`mpl.figure.Figure`
        The :class:`mpl.figure.Figure` instance to commit.
    name: str
        The string name given to the figure.

    Other Parameters
    ----------------
    category: str, default=None
        The figure category to assign to this figure.
        Possible values are given in :obj:`do.commodities.VALID_FIGURE_CATEGORIES`.
    watermark: str, default = None
        If the `plots.watermark.show` setting is True, print this watermark on the figure.
        Note that the default watermark (from `plots.watermark.default` setting) is always added, even if this argument is None.
    config_uid: str, default=None
        The unique ID to associate this figure with.
        This is typically a configuration UID, as return by :meth:`Calibration.uid`.
    dest: Path, default=do.tmp_root()
        Destination folder of the figure pickle file.
        This is not the report output and this folder is likely temporary.
    """
    if name.strip() == "" or name is None:
        raise ValueError("A figure must have a name to be commited")

    # Create a PydoxFigure instance with these figure and meta-data:
    this_f = PydoxFigure(fig=fig, name=name, category=category, config_uid=config_uid)

    # Check, by uid, if the figure was already committed:
    found = False
    for f in do.__figures:
        if this_f.uid == f.uid:
            found = True

    # If not found, commit this:
    if not found:
        print(
            f"Commit figure '{this_f.name}' (level {this_f.level} / {this_f.category})"
        )

        # Print watermark:
        print_watermark: bool = do.get_params("plots.watermark.show")
        default_watermark: str = do.get_params("plots.watermark.default")

        if print_watermark and (watermark is not None or default_watermark is not None):
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
        pkl = dest.joinpath(f"{this_f.uid}.pkl")
        with open(pkl, "wb") as fid:
            pickle.dump(this_f.fig, fid)
        this_f.pickle = pkl  # Update PydoxFigure path to the appropriate pickle file

        # Add this PydoxFigure instance to the internal global registry:
        do.__figures.append(this_f)

    # Close figure upon commit:
    # Showing is controlled by higher-level methods, such as Calibration.plot()
    mpl.pyplot.close(fig)
