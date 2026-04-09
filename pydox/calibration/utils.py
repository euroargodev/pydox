from typing import Any

from pydox.commodities import ParameterSet


def params2cycs(params: ParameterSet, data: Any) -> list[int]:
    """Return the explicit first and last cycle numbers to work with, based on the 'cycles' parameter

    This function allows to use natural language values like 'first' or 'last' in ParamsInAir commodity class

    Here, we return real cycle numbers.
    """
    if params.cycles[0] == "first":
        cycle_first = 1  # or read from data
    else:
        raise NotImplementedError
    if params.cycles[-1] == "last":
        cycle_last = len(data["PPOX1"])
    else:
        raise NotImplementedError

    return [cycle_first, cycle_last]

