"""
Some documentation in here, before moving it to 'docs' later.

## Definitions

The Pydox configuration set of parameters is defined in two, complementary, ways:

- The "default configuration" that is set from **configuration files** loaded at import time,
- The "on-demand configuration" that is set by users **in scripts**, using Pydox dedicated API methods.

## About configuration parameters
- They are organized into groups and possibly subgroups.
- There is no limit to subgroups nesting depth.
- Groups, subgroups and parameters are meant to be accessed (get/set methods) with a _string-dotted_ syntax, eg:
    - ``'argo'`` is a _group_,
    - ``'argo.qcflags'`` is a _subgroup_,
    - ``'argo.qcflags.temp'`` is a _parameter_ name.
- Can be **read/get**, using the _string-dotted_ syntax, with ``do.get_params()``
- Can be **set**, using the _string-dotted_ syntax, with ``do.set_params()``

## About the full set of configuration parameters
- It is assumed to be an object of type: dict[str, Any]. But this could change in the future.
- The "default configuration" is constructed when Pydox is imported with ``do.config.load_configs()`` by a sequential loading sequence of possibly several files looked for in builtin locations (but possibly customized with environment variables). This sequence of files can be returned by ``do.config_files()``.

- The ordered list of all possible "default configuration" files is:
    - From the Pydox distribution (_factory_ configuration), ie where Pydox is installed, eg:
        - ``${HOME}/bin/yes/envs/pydox-dev/lib/python3.11/site-packages/pydox/static/pydoxrc``
    - From the user configuration folder, eg:
        - ``${PYDOXCONFIGDIR}/pydoxrc`` or
        - ``${XDG_CONFIG_HOME}/pydox/pydoxrc`` or
        - ``${HOME}/.config/pydox/pydoxrc`` or
        - ``${HOME}/.pydox/pydoxrc``
    - From the executing environment, ie from the environment variable:
        - ``${PYDOXRC}`` or
        - ``${PYDOXRC}/pydoxrc``
    - From current executing path, ie from the environment variable:
        - ``${PWD}/pydoxrc``

- The object with the full set of configuration parameters is accessible as: ``do.params``.

- The object ``do.params`` is NOT meant to be modified directly (huge risk of un-expected side effects): internals and users should use the ``do.set_params()`` method instead.

## Environment variables
Here is the list of relevant environment variables that can be used to customize where to look for default configuration files (see documentation):
- ``PYDOXCONFIGDIR``
- ``XDG_CONFIG_HOME``
- ``PYDOXRC``

"""


# ‼️ This is the only module where the global configuration object is to be referred to as ``rcParams``

import importlib
from pathlib import Path
from matplotlib.rcsetup import validate_stringlist

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

from pydox.config.yaml import load_config_from_file


log = logging.getLogger("pydox.config")

_path2static = importlib.util.find_spec("pydox.static").submodule_search_locations[0]

_valid_config_version = "0.1"

# List of parameters (group, subgroup, key) that are read-only,
# (i.e. cannot be modified with ``do.set_params``):
_read_only_dotted_params = ["version"]  # use lower-dotted string format

# List of parameters (group, subgroup, key) that are NOT over-writen when loading the sequence of config. files,
# (i.e. default package distribution values are read-only):
_not_overloaded_dotted_params = ["version"]  # use lower-dotted string format


def _get_xdg_config_dir() -> str:
    """Return the XDG configuration directory

    According to the XDG base directory spec:
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
    """Get the list of all available configuration files to build a _default_ configuration

    List of all possible files:
    - From factory, ie where pydox is installed, eg:
        - ``${HOME}/bin/yes/envs/pydox-dev/lib/python3.11/site-packages/pydox/static/pydoxrc``
    - From the user configuration folder, eg:
        - ``${PYDOXCONFIGDIR}/pydoxrc`` or
        - ``${XDG_CONFIG_HOME}/pydox/pydoxrc`` or
        - ``${HOME}/.config/pydox/pydoxrc`` or
        - ``${HOME}/.pydox/pydoxrc``
    - From the executing environment, ie from the environment variable:
        - ``${PYDOXRC}`` or
        - ``${PYDOXRC}/pydoxrc``
    - From the current executing path, ie from the environment variable:
        - ``${PWD}/pydoxrc``

    Returns
    -------
    list[Path]
        A list of absolute paths toward default configuration files.
        The first file is always the _factory_ configuration file.

    See Also
    --------
    :function:`load_configs`
    """

    def gen_candidates() -> Generator[Path, None, None]:
        yield Path(_path2static).joinpath("pydoxrc")
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

    This will ensure that even partial (sub)group custom settings can be done (eg: use a custom config to modify ``argo.qcflags.pres`` only, without necessarily needing to redefine the entire subgroup ``argo.qcflags``.

    Parameters
    ----------
    x: dict[str, Any]
        A configuration set of parameters, possibly loaded from a file
    y: dict[str, Any]
        A configuration set of parameters, possibly loaded from a file

    Returns
    -------
    dict[str, Any]
        A deep copy of x, with updated values from y
    """
    z = deepcopy(x)
    for key in flatten_config_keys(y):
        if key.lower() not in _not_overloaded_dotted_params:
            set_by_path(z, key, get_by_path(y, key))
    return z


def load_factory_config() -> dict[str, Any]:
    """Load the _factory_ configuration, ie from the internal static file

    This file is always available, otherwise the Pydox installation is totally broke !

    Returns
    -------
    dict[str, Any]

    See Also
    --------
    :function:`reset_params`
    """
    file_list = config_files()
    return load_config_from_file(file_list[0]) # _factory_ config is always the first one


def load_configs()-> dict[str, Any]:
    """Load the _default_ configuration from the sequence of all possible configuration files

    Returns
    -------
    dict[str, Any]
        Default Pydox configuration object

    See Also
    --------
    :function:`config_files`
    """
    file_list = config_files()
    C = load_config_from_file(file_list[0])
    for f in file_list[1:]:
        c = load_config_from_file(f)
        if get_by_path(c, "version") == _valid_config_version:
            C = overload_config(C, c)
        else:
            raise ValueError(
                f"Invalid configuration file format version {get_by_path(c, 'version')}, must be {_valid_config_version}"
            )
    return C


def get_by_path(config: Dict | List, key: str) -> Any:
    """Access an item from a nested object config with a string-dotted key

    Parameters
    ----------
    config: Dict | List
        Nested object, typically a configuration set of nested dictionaries
    key: str
        A string-dotted key pointing to an item from config (eg: ``argo.qcflags``)

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
        A string-dotted key pointing to an item from config to be set (eg: ``operator.name``)
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


def get_params(param: str, config: Any = None) -> Any | Dict:
    """Retrieve the value of a configuration parameter or (sub)group of parameters

    Parameters
    ----------
    param: str
        The parameter name or (sub)group of parameters.
        Use a string-dotted notation if necessary, eg:

        - ``argo.qcflags.doxy`` will return this single parameter value,
        - ``argo.qcflags`` will return a subgroup of parameters, as a :class:`dict`,
        - ``argo`` will return a group of parameters, as a :class:`dict`.
    config: None | dict[str, Any]
        The configuration object to get parameters from.
        By default, use the global configuration object :class:`pydox.params`.

    Returns
    -------
    Any | Dict
        The parameter value or group of parameters

    See Also
    --------
    :function:`set_params`, :function:`reset_params`
    """
    # Which configuration to work with:
    config = rcParams if config is None else config

    return get_by_path(config, param)


def set_params(param: str, value: Any | Dict, config: Any = None) -> Any | Dict:
    """Set the value of a configuration parameter or (sub)group of parameters

    Parameter or (sub)groups of parameters are modified _in place_.

    Parameters
    ----------
    param: str
        The parameter name or (sub)group of parameters.
        Use a string-dotted notation if necessary, eg:

        - ``argo.qcflags.doxy`` set a single parameter value,
        - ``argo.qcflags`` set a subgroup of parameters, expect value as a :class:`dict`,
        - ``argo`` set a group of parameters, expect value as a :class:`dict`,
    value: Any, Dict
        The value to assigne to ``param``.
    config: None | dict[str, Any]
        The configuration object to set parameters to.
        By default, use the global configuration object :class:`pydox.params`.

    Returns
    -------
    Any | Dict
        The parameter value or group of parameters that has just been set

    See Also
    --------
    :function:`get_params`, :function:`reset_params`
    """
    # Which configuration to work with:
    config = rcParams if config is None else config

    set_by_path(config, param, value)
    return value


def reset_params(param: str = None, config: Any = None, factory: bool = False, **kwargs) -> None:
    """Reset a configuration parameter to default values

    _Default_ values are those from the sequential loading of all available configuration files.

    Parameter or (sub)groups of parameters are modified _in place_.

    Parameters
    ----------
    param: str
        The parameter name or (sub)group of parameters.
        Use a string-dotted notation if necessary, eg:

        - ``argo.qcflags.doxy`` reset a single parameter value,
        - ``argo.qcflags`` reset a subgroup of parameters,
        - ``argo`` reset a group of parameters.
    config: None | dict[str, Any]
        The configuration object to reset parameters from.
        By default, use the global configuration object :class:`pydox.params`.
    factory: bool, default=False
        Set this argument to True in order to reset with _factory_ values instead of _default_ values. Factory values ignore user specific configuration files and is solely based on the Pydox internal static file.

    Other Parameters
    ----------------
    reference: dict[str, Any]
        The configuration object to use as a reference if different from the _default_ or _factory_ objects. This argument is primarily for internal use only.

    Returns
    -------
    None

    See Also
    --------
    :function:`get_params`, :function:`set_params`
    """

    # Which configuration to work with:
    config = rcParams if config is None else config

    # Get a list of parameters to reset:
    if param is None:
        # Work with all parameters:
        params = flatten_config_keys(config)
    else:
        # Make sure we have a list:
        params = validate_stringlist(param)

    # Define the configuration to be considered as a reference:
    # (from which reset values are to be read)
    if 'reference' not in kwargs:
        if factory:
            reference_config = load_factory_config()
        else:
            reference_config = load_configs()
    else:
        reference_config = kwargs['reference']

    # Loop through all parameters and reset them (set values from reference configuration):
    for p in params:
        if p not in _read_only_dotted_params:
            reference_value = get_params(p, config=reference_config)
            set_params(p, reference_value, config=config)

# Load the default configuration to be used globally as `do.params`:
rcParams = load_configs()
