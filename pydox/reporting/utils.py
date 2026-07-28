from typing import List
from collections import OrderedDict

import pydox as do
from pydox.commodities import PydoxFigure


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
