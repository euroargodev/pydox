"""

We assume that a configuration object is of type: dict[str, Any]

Relevant environment variables:
PYDOXRC
XDG_CONFIG_HOME
PYDOXCONFIGDIR
"""

import importlib
from pathlib import Path
import yaml
import re
import os
import sys
from functools import reduce
import operator
from typing import List, Dict, Any, Generator
from copy import deepcopy
import tempfile
import shutil
import atexit
import logging


log = logging.getLogger("pydox.config")

path2static = importlib.util.find_spec("pydox.static").submodule_search_locations[0]

path_matcher = re.compile(r"\$\{([^}^{]+)\}")

valid_config_version = "0.1"

_read_only_dotted_params = ["version"]  # user lower-dotted string format

_not_overloaded_dotted_params = ["version"]  # user lower-dotted string format


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


def _get_xdg_config_dir() -> str:
    """Return the XDG configuration directory, according to the XDG base directory spec:

    https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html

    Adapted from Matplotlib:
    https://github.com/matplotlib/matplotlib/blob/v3.10.8/lib/matplotlib/__init__.py#L503
    """
    return os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")


def get_configdir() -> str:
    """Return the string path of the user configuration directory.

    The directory is chosen as follows:

    1. If the PYDOXCONFIGDIR environment variable is supplied, choose that.
    2. - On Linux, follow the XDG specification:
         - and look first in ``$XDG_CONFIG_HOME``, if defined,
         - or ``$HOME/.config``.
       - On other platforms, choose ``$HOME/.pydox``.
    3. If the chosen directory exists and is writable, use that as the configuration directory.
    4. Else, create a temporary directory, and use it as the configuration directory.

    Adapted from Matplotlib:
    https://github.com/matplotlib/matplotlib/blob/v3.10.8/lib/matplotlib/__init__.py#L564
    """
    configdir = os.environ.get("PYDOXCONFIGDIR")
    if configdir:
        configdir = Path(configdir)
    elif sys.platform.startswith(("linux", "freebsd")):
        configdir = Path(_get_xdg_config_dir(), "pydox")
    else:
        configdir = Path.home() / ".pydox"
    configdir = (
        configdir.resolve()
    )  # Make the path absolute, resolving any symlinks. A new path object is returned

    try:
        configdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("mkdir -p failed for path %s: %s", configdir, exc)
    else:
        if os.access(str(configdir), os.W_OK) and configdir.is_dir():
            return str(configdir)
        log.warning("%s is not a writable directory", configdir)

    # If the config or cache directory cannot be created or is not a writable
    # directory, create a temporary one.
    try:
        tmpdir = tempfile.mkdtemp(prefix="pydox-")
    except OSError as exc:
        raise OSError(
            f"Pydox requires access to a writable cache directory, but there "
            f"was an issue with the default path ({configdir}), and a temporary "
            f"directory could not be created; set the PYDOXCONFIGDIR environment "
            f"variable to a writable directory"
        ) from exc
    os.environ["PYDOXCONFIGDIR"] = tmpdir
    atexit.register(shutil.rmtree, tmpdir)  # to be executed at program termination
    log.warning(
        "Pydox created a temporary cache directory at %s because there was "
        "an issue with the default path (%s); it is highly recommended to set the "
        "PYDOXCONFIGDIR environment variable to a writable directory, in particular to "
        "speed up the import of Pydox and to better support multiprocessing.",
        tmpdir,
        configdir,
    )
    return tmpdir


def config_files() -> list[Path]:
    """Get the location of all config files

    All possible pydoxrc files:
    - From distribution (where pydox is installed), eg: '/Users/gmaze/git/github/euroargodev/pydox/pydox/static/pydoxrc'
    - From user configuration, eg: '/Users/gmaze/.pydox/pydoxrc', '/Users/gmaze/.config/pydox/pydoxrc'
    - From current executing path, eg: '/Users/gmaze/git/github/euroargodev/pydox/local_work/pydoxrc'
    """

    def gen_candidates() -> Generator[Path, None, None]:
        yield Path(path2static).joinpath("pydoxrc")
        yield Path(get_configdir()).joinpath("pydoxrc")
        try:
            pydoxrc = os.environ["PYDOXRC"]
        except KeyError:
            pass
        else:
            yield Path(pydoxrc)
            yield Path(pydoxrc).joinpath("pydoxrc")
        yield Path(os.environ.get("PWD")).joinpath("pydoxrc")

    return [
        fname.resolve()
        for fname in gen_candidates()
        if os.path.exists(fname) and not os.path.isdir(fname)
    ]


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
        if key.lower() not in _not_overloaded_dotted_params:
            set_by_path(z, key, get_by_path(y, key))
    return z


def load_default_config() -> dict[str, Any]:
    """Load default configuration file from internal static file

    This file is always here, otherwise pydox installation is totally broke !

    Returns
    -------
    dict[str, Any]
    """
    return load_config_from_file(Path(path2static).joinpath("pydoxrc"))


def load_configs():
    """Cumulative load of configuration files"""
    file_list = config_files()
    C = load_config_from_file(file_list[0])
    for f in file_list[1:]:
        c = load_config_from_file(f)
        if get_by_path(c, "version") == valid_config_version:
            C = overload_config(C, c)
        else:
            raise ValueError(
                f"Invalid configuration file format version {get_by_path(c, 'version')}, must be {valid_config_version}"
            )
    return C


def get_by_path(config: Dict | List, key: str) -> Any:
    """Access an item from a nested object config with a string-dotted key

    Parameters
    ----------
    config: Dict | List
        Nested object, typically a configuration set of nested dictionaries
    key: str
        A string-dotted key pointing to an item from config (eg: 'argo.qcflags')

    Returns
    -------
    Any
    """
    key = key.split(".")
    return reduce(operator.getitem, key, config)


def set_by_path(config: Dict | List, key: str, value: Any) -> Dict | List:
    """Set a value in a nested object config with a string-dotted key

    Parameters
    ----------
    config: Dict | List
        Nested object, typically a configuration set of nested dictionaries
    key: str
        A string-dotted key pointing to an item from config to be set (eg: 'operator.name')
    value: Any
        New value for key in config

    Returns
    -------
    Dict | List
        Updated config object
    """
    if key.lower() in _read_only_dotted_params:
        raise ValueError(f"Parameter '{key}' is read-only !")
    key = key.split(".")
    if len(key) > 1:
        group = get_by_path(config, ".".join(key[:-1]))
        group[key[-1]] = value
    else:
        config[key[0]] = value
    return config


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
    C = load_configs()
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
        Full configuration, to allow for chaining
    """
    C = load_configs()
    return set_by_path(C, param, value)
