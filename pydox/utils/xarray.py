import xarray as xr
import pandas as pd
from pydox.utils.casting import to_list


def xr_append_history(
    this_obj: xr.Dataset | xr.DataArray,
    new_entry: str | list[str] = None,
    attr: str = "history",
) -> xr.Dataset | xr.DataArray:
    """Append a new entry to the history attribute"""
    if attr in this_obj.attrs:
        history = this_obj.attrs[attr].split(";")
        history = [l.strip() for l in history]
    else:
        history = []
    if new_entry is not None:
        for line in to_list(new_entry):
            if ";" in line:
                raise ValueError(
                    "Adding a new entry to the history attribute with a semi-colon is forbidden, as it is the entry separator."
                )
            ts = (
                pd.to_datetime("now", utc=True)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
            new_line = f"{ts} {line}"
            history.append(new_line)
    this_obj.attrs[attr] = ";".join(history)
    return this_obj
