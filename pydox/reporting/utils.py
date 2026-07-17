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
    dest: Optional[Path] = None,
    config_uid: Optional[str] = None,
):
    """Commit a named :mpl:`Figure` object to the global registry

    The :mpl:`Figure` object is automatically pickled (in a tmp folder) for later re-open or re-use in the session.
    The :mpl:`Figure` object is also closed upon commit.
    """
    if name.strip() == "" or name is None:
        raise ValueError("A figure must have a name to be commited")

    new_f = PydoxFigure(fig=fig, name=name, config_uid=config_uid)

    found = False
    for f in do.__figures:
        if new_f.uid == f.uid:
            found = True

    if not found:
        dest = do.tmp_root() if dest is None else Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        pkl = dest.joinpath(f"{new_f.uid}.pkl")
        with open(pkl, "wb") as fid:
            pickle.dump(new_f.fig, fid)

        new_f.pickle = pkl
        do.__figures.append(new_f)
        mpl.pyplot.close(fig)


def configs_figure_list(obj) -> OrderedDict[int, List[PydoxFigure]]:
    """Create a dictionary of figures for a given object with a `configs` attribute of type ConfigsDict"""
    results = OrderedDict()
    for iset, params in obj.configs.items():
        results[iset]: List[PydoxFigure] = []
        for f in do.__figures:
            if f.config_uid.startswith(obj.uid(iset)):
                results[iset].append(f)
    return results
