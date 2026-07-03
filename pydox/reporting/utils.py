from pathlib import Path
import pickle
from typing import Optional
import pydox as do
from pydox.commodities import Figure


def fig_commit(
    fig, name: str, dest: Optional[Path] = None, caller_uid: Optional[str] = None
):
    new_f = Figure(fig=fig, name=name, caller=caller_uid)

    found = False
    for f in do.__figures:
        if new_f.uid == f.uid:
            found = True

    if not found:
        do.__figures.append(new_f)

        dest = do.tmp_root if dest is None else Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        with open(dest.joinpath(f"{new_f.uid}.pkl"), "wb") as fid:
            pickle.dump(new_f.fig, fid)


def tmp_setup(root: Path | str, wmo: Optional[int | str] = None) -> Path:
    """

    tmp_setup(do.get_params('output.root'), af.WMO)

    Parameters
    ----------
    af
    cfg

    Returns
    -------

    """
    if wmo is None:
        root = Path(root)
    else:
        root = Path(root).joinpath(f"{wmo}")
    root.mkdir(parents=True, exist_ok=True)

    tmp_root = root.joinpath("tmp")
    tmp_root.mkdir(parents=True, exist_ok=True)

    return tmp_root
