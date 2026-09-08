# ‼️ This is the only module where the global configuration object is to be referred to as ``rcParams`` and not ``do.params``
# ‼️ This is the only module where the pydox logger cannot be used

import importlib
from pathlib import Path
from matplotlib.rcsetup import validate_stringlist
import os
import sys
import operator
from typing import List, Dict, Any, Generator, TypeAlias
from copy import deepcopy
import tempfile
import shutil
import atexit
import logging
from IPython.display import HTML
import argopy as ar


from pydox._config import (
    _valid_config_version,
    _read_only_dotted_params,
    _not_overloaded_dotted_params,
)
from pydox._config.utils import reduce, runner, config_repr_txt, config_repr_html
from pydox._config.yaml import load_config_from_file
from pydox.errors import MissingSetting

# from pydox.reporting.logs import getLogger # Impossible without circularity, _config is only module where we cant use getLogger


log = logging.getLogger("pydox.config")
Config: TypeAlias = Dict[str, Any]

_path2static = Path(
    importlib.util.find_spec("pydox.static").submodule_search_locations[0]
)


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
        yield _path2static.joinpath("pydoxrc")
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


def flatten_config_keys(d: Config, parent_key: str = "", sep: str = ".") -> list[str]:
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
        A list of dotted strings representing all possible keys. Case-sensitive
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_config_keys(v, new_key, sep=sep))
        else:
            items.append(new_key)
    return items


def overload_config(x, y) -> Config:
    """Overload configuration x with values from configuration y

    Overloading is done one parameter at a time, whatever the nesting depth using the dotted.string pattern.

    This will ensure that even partial (sub)group custom settings can be done (eg: use a custom config to modify ``argo.qcflags.pres`` only, without necessarily needing to redefine the entire subgroup ``argo.qcflags``.

    Parameters
    ----------
    x: Config
        A configuration set of parameters, possibly loaded from a file
    y: Config
        A configuration set of parameters, possibly loaded from a file

    Returns
    -------
    Config
        A deep copy of x, with updated values from y
    """
    z = deepcopy(x)
    for key in flatten_config_keys(y):
        if key.lower() not in _not_overloaded_dotted_params:
            # log.debug(f"Overloading {key}")
            set_by_path(z, key, get_by_path(y, key))
    return z


def load_factory_config() -> Config:
    """Load the _factory_ configuration, ie from the internal static file

    This file is always available, otherwise the Pydox installation is totally broke !

    Returns
    -------
    Config

    See Also
    --------
    :function:`reset_params`
    """
    file_list = config_files()
    return load_config_from_file(
        file_list[0]
    )  # _factory_ config is always the first one


def load_configs() -> Config:
    """Load the _default_ configuration from the sequence of all possible configuration files

    Returns
    -------
    Config
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
    # Sort dict key alphabetically:
    C = dict(sorted(C.items()))

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

        # Make sure that all subgroups exist (even empty)
        # This allows to apply a setting even if the parent subgroup do not exist before.
        # Eg:
        # to set `reports.templates.new_template.name`,
        # requires ``reports.templates.new_template` subgroup to exist
        for ik in range(1, len(key)):
            try:
                get_by_path(config, ".".join(key[:ik]))
            except MissingSetting:
                group = get_by_path(config, ".".join(key[: ik - 1]))
                group[key[ik - 1]] = {}

        #
        group = get_by_path(config, ".".join(key[:-1]))
        group[key[-1]] = value  # This modifies group in config in place

    else:
        config[key[0]] = value
    return config


def hint_params(key: str, **kwargs) -> list[str] | None:
    """Return striong-dotted parameter hints for a given key"""

    # Which configuration to work with:
    config = kwargs.get("config", rcParams)

    # Get the full list of all possible string-dotted parameter pointers:
    flat_keys = flatten_config_keys(config)

    key_hint = []
    for k in flat_keys:
        if key in k.split("."):
            key_hint.append(k)

    return key_hint


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
    config: None | Config
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


def set_params(param_or_grp: str, value: Any | Dict = None, **kwargs) -> None:
    """Set the value of a configuration parameter or (sub)group of parameters

    Parameter or (sub)groups of parameters are modified _in place_.

    Parameters
    ----------
    param_or_grp: str
        The parameter name or (sub)group of parameters to assign value(s) to.
        Use a string-dotted notation if necessary, eg:

        - ``argo.qcflags.doxy`` set a single parameter value,
        - ``argo.qcflags`` set a subgroup of parameters, expect value as a :class:`dict` or with keyword arguments.
        - ``argo`` set a group of parameters, expect value as a :class:`dict` or with keyword arguments.
    value: Any, Dict, default=None
        The value to be assigned to ``param_or_grp``.
        If set to None, assume to be setting a group of parameters using keyword arguments (see examples below).
    **kwargs:
        Use keyword arguments to set parameters for a (sub)group (see examples below).

    Other Parameters
    ----------------
    config: None | Config
        The configuration object to set parameters to.
        By default, use the global configuration object :class:`pydox.params`.

    See Also
    --------
    :function:`get_params`, :function:`reset_params`

    Examples
    --------
    ..code-block: python
        :caption: Set one parameter value

        # Directly:
        do.set_params('argo.qcflags.psal', [1, 2, 8])
        # or at the subgroup level:
        do.set_params('argo.qcflags', psal=[1, 2, 8])
        # or at the group level:
        do.set_params('argo', qcflags={'psal': [1, 2, 8]})

    ..code-block: python
        :caption: Set a (sub)group of parameter values

        # At the subgroup level:
        # with keywords:
        do.set_params('argo.qcflags', psal=[1, 2, 8], temp=[1, 2, 8])
        # or a dictionary:
        do.set_params('argo.qcflags', {'psal': [1, 2, 8], 'temp': [1, 2, 8]})

        # At the group level:
        # with keywords:
        do.set_params('argo', qcflags={'psal': [1, 2, 8], 'temp': [1, 2, 8]})
        # or a nested dictionary:
        do.set_params('argo', {'qcflags': {'psal': [1, 2, 8], 'temp': [1, 2, 8]}})
    """

    # Which configuration to work with:
    config = kwargs.get("config", rcParams)
    if "config" in kwargs:
        kwargs.pop("config")

    # Get the full list of all possible string-dotted parameter pointers:
    flat_keys = flatten_config_keys(config)

    def _flatten(root: str, current_key: str, value: Any) -> None:
        """Recursively flatten nested dictionaries into dotted_params."""
        if isinstance(value, dict):
            for k, v in value.items():
                _flatten(
                    root, f"{root}.{k}" if not current_key else f"{current_key}.{k}", v
                )
        else:
            if f"{root}.{current_key}" in flat_keys:
                dotted_params[f"{root}.{current_key}"] = value
            else:
                msg = f"Trying to set an unknown parameter '{root}.{current_key}'."
                hints = hint_params(current_key, config=config)
                if len(hints) > 0:
                    msg += f" Maybe you were trying to set one the following parameters: {hints}."
                raise ValueError(msg)

    # Create a dictionary with string-dotted parameter pointers as keys, and new values as values
    dotted_params = {}
    if value is None:

        if isinstance(param_or_grp, dict):
            # DOES NOT Handle use case like: set_params({string-dotted: value})
            # eg: do.set_params({'argo.qcflags.psal': [1, 2, 8]})
            raise ValueError("set_params does not support dictionaries")

        else:
            # Handle use case like: set_params(string-dotted, key=val, key=val, key=val)
            # eg:
            # do.set_params('argo.qcflags', psal=[1, 2, 8])
            # do.set_params('argo', qcflags={'psal': [1, 2, 8], 'temp': [1, 2, 8]})
            # do.set_params('argo.qcflags', psal=[1, 2, 8], temp=[1, 2, 8])
            for key, value in kwargs.items():
                _flatten(param_or_grp, key, value)

    else:
        if isinstance(value, dict):
            # Handle use case like set_params(string-dotted, dict):
            # do.set_params('argo', {'qcflags': {'psal': [1, 2, 8], 'temp': [1, 2, 8]}})
            for k, v in value.items():
                _flatten(param_or_grp, k, v)

        else:
            # Handle use case like set_params(string-dotted, value):
            # do.set_params('argo.qcflags.psal', [1, 2, 8])
            dotted_params.update({param_or_grp: value})

    # Apply new values:
    for key, value in dotted_params.items():
        set_by_path(config, key, value)

    # Possibly trigger specific actions when a given setting is modified:
    if next(
        (value for key, values in dotted_params.items() if key == "reports.template"),
        None,
    ):
        log.debug(
            f"Setting 'reports.template' is updated to '{value}': re-loading templates..."
        )
        import pydox as do

        do.reporting.facade.load_template()


def reset_params(
    param: str = None, config: Any = None, factory: bool = False, **kwargs
) -> None:
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
    config: None | Config
        The configuration object to reset parameters from.
        By default, use the global configuration object :class:`pydox.params`.
    factory: bool, default=False
        Set this argument to True in order to reset with _factory_ values instead of _default_ values. Factory values ignore user specific configuration files and is solely based on the Pydox internal static file.

    Other Parameters
    ----------------
    reference: Config
        The configuration object to use as a reference if different from the _default_ or _factory_ objects. This argument is primarily for internal use only.

    Returns
    -------
    None

    See Also
    --------
    :function:`get_params`, :function:`set_params`

    Warnings
    --------
    If for some reason the current configuration has lost some parameters compared to the _default_ configuration, this
    reset method cannot restore them, it only applies to parameters currently in the configuration.
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
    if "reference" not in kwargs:
        if factory:
            reference_config = load_factory_config()
        else:
            reference_config = load_configs()
    else:
        reference_config = kwargs["reference"]

    # Loop through all parameters and reset them (set values from reference configuration):
    # We ignore parameters starting with an underscore "_" because they are considered private and managed differently.
    for p in params:
        if p not in _read_only_dotted_params and not p.split(".")[-1].startswith("_"):
            reference_value = get_params(p, config=reference_config)
            set_params(p, reference_value, config=config)


def config_print(config: Config = None, **kwargs) -> str | HTML:
    """Render a configuration object as text or HTML

    Parameters
    ----------
    config : Config, default = None
        A configuration object to print.
        By default, use the global configuration object :class:`pydox.params`.

    Returns
    -------
    str | HTML
        A pretty-printed string representation of the configuration.
    """
    # Which configuration to work with:
    config = rcParams if config is None else config

    if runner() in ["notebook"]:
        return HTML(config_repr_html(config, **kwargs))
    else:
        return print(config_repr_txt(config), **kwargs)


def check_config(obj: Any) -> Config:
    """Check if the object is a valid configuration or not, raise an error on fail

    Raises
    ------
    ValueError
    """
    try:
        "version" in obj
        return obj
    except:
        raise ValueError("This is not a valid configuration object")


def is_config(obj: Any) -> bool:
    """Check if an object is a valid configuration

    This method won't raise an error if the object is not a valid configuration. To raise an error, use :function:`check_config`

    Returns
    -------
    bool
        Is this a valid configuration object or not

    See Also
    --------
    :function:`check_config`
    """
    try:
        check_config(obj)
        return True
    except ValueError:
        return False


# Load the default configuration to be used globally as `do.params`:
# (because we load pydox._config.config.rcParams as params from pydox.__init__)
rcParams = load_configs()

# Also update Argopy options accordingly:
ar.set_options(gdac=get_params("argo.src"))
log.info(f"Pydox has set the Argopy option 'gdac' to '{get_params('argo.src')}'")
