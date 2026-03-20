"""

We assume that a configuration object is of type: dict[str, Any]

A configuration is loaded from a file
"""

import importlib
from pathlib import Path
import yaml
import re
import os
from functools import reduce
import operator
from typing import List, Dict, Any
from copy import deepcopy


path2static = importlib.util.find_spec("pydox.static").submodule_search_locations[0]


path_matcher = re.compile(r"\$\{([^}^{]+)\}")


def path_constructor(loader, node):
    """Extract the matched value, expand env variable, and replace the match"""
    value = node.value
    match = path_matcher.match(value)
    env_var = match.group()[2:-1]
    return os.environ.get(env_var) + value[match.end() :]


yaml.add_implicit_resolver("!path", path_matcher, None, yaml.SafeLoader)
yaml.add_constructor("!path", path_constructor, yaml.SafeLoader)


def load_config_from_file(fname: str | Path) -> dict[str, Any]:
    """Load a pydoxrc configuration file"""
    with open(Path(fname), "r") as f:
        cfg = yaml.load(f, Loader=yaml.SafeLoader)
    return cfg


def load_default_config() -> dict[str, Any]:
    """Load default configuration file from internal static file

    This file is always here, otherwise pydox installation is totally broke !

    Returns
    -------
    dict[str, Any]
    """
    return load_config_from_file(Path(path2static).joinpath("pydoxrc"))


def load_home_config():
    pass


def flatten_config_keys(
    d: dict[str, Any], parent_key: str = "", sep: str = "."
) -> list[str]:
    """Flatten a nested dictionary into a list of dotted strings representing all possible keys.

    Parameters
    ----------
    d: dict
        The dictionary to flatten.
    parent_key: str, optional, default=""
        The string representing the parent key (used for recursion).
    sep: str, optional, default="."
        The separator to use between keys.

    Returns
    -------
    list[str]:
        A list of dotted strings representing all possible keys.
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_config_keys(v, new_key, sep=sep))
        else:
            items.append(new_key)
    return items


def overload_config(x, y) -> dict[str, Any]:
    """Overload configuration x with values from configuration y

    Overloading is done one parameter at a time, whatever the nesting depth using the dotted.string pattern.

    This will ensure that even partial (sub)group custom settings can be done (eg: use a custom config to modify 'argo.qcflags.pres' only, without necessarily needing to define the entire subgroup 'argo.qcflags'.

    Parameters
    ----------
    x: dict[str, Any]
        A configuration set of parameters, possibly loaded from a file
    y: dict[str, Any]
        A configuration set of parameters, possibly loaded from a file

    Returns
    -------

    """
    z = deepcopy(x)
    for key in flatten_config_keys(y):
        set_by_path(z, key, get_by_path(y, key))
    return z


def load_config() -> dict[str, Any]:
    # Load default configuration from distribution:
    C = load_default_config()

    # Merge with more user-defined configuration files:
    # C = overload_config(C, load_home_config())

    # C = overload_config(C, load_env_config())

    # C = overload_config(C, load_local_config())

    return C


def get_by_path(root: Dict | List, key: str) -> Any:
    """Access an item from a nested object root with a string-dotted key

    Parameters
    ----------
    root: Dict | List
        Nested object, typically a configuration set of nested dictionaries
    key: str
        A string-dotted key pointing to an item from root (eg: 'argo.qcflags')

    Returns
    -------
    Any
    """
    key = key.split(".")
    return reduce(operator.getitem, key, root)


def set_by_path(root: Dict | List, key: str, value: Any) -> Dict | List:
    """Set a value in a nested object with a string-dotted key

    Parameters
    ----------
    root: Dict | List
        Nested object, typically a configuration set of nested dictionaries
    key: str
        A string-dotted key pointing to an item from root to be set (eg: 'operator.name')
    value: Any
        New value for key in root

    Returns
    -------
    Dict | List
        Updated root object
    """
    key = key.split(".")
    get_by_path(root, ".".join(key[:-1]))[key[-1]] = value
    return root


def get_params(param: str) -> Any | Dict:
    """Retrieve the value of a configuration parameter or (sub)group of parameters

    Parameters
    ----------
    param: str
        The parameter name or (sub)group of parameters.
        Use a 'dotted' notation if necessary, eg:

        - 'argo.qcflags.doxy' will return this single parameter value,
        - 'argo.qcflags' will return a subgroup of parameters, as a :class:`dict`,
        - 'argo' will return full group of parameters, as a :class:`dict`.

    Returns
    -------
    Any | Dict
        The parameter value or group of parameters
    """
    C = load_config()
    return get_by_path(C, param)


def set_params(param: str, value: Any | Dict) -> dict[str, Any]:
    """Set value of a configuration parameter or (sub)group of parameters

    Parameters
    ----------
    param: str
        The parameter name or (sub)group of parameters.
        Use a 'dotted' notation if necessary, eg:

        - 'argo.qcflags.doxy' set a single parameter value,
        - 'argo.qcflags' set a subgroup parameter, expect a :class:`dict`,
        - 'argo' set a group parameter, expect a :class:`dict`,
    value: Any, Dict
        The value to assigne to ``param``.

    Returns
    -------
    dict[str, Any]:
        Full configuration to allow for chaining
    """
    C = load_config()
    return set_by_path(C, param, value)
