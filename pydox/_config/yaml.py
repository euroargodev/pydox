import yaml
import re
import os
from pathlib import Path
from typing import Any


# Regexp to recognize reference to environment variables (eg: '${HOME}'):
_osenv_matcher = re.compile(r"\$\{([^}^{]+)\}")


def osenv_constructor(loader, node) -> str:
    """Create a constructor to replace environment variables by their value when a YAML file is loaded

    A YAML constructor is a function that accepts a Loader instance and a node object and produces the corresponding Python object.

    Parameters
    ----------
    loader: :class:`yaml.BaseLoader`, :class:`yaml.FullLoader`, :class:`yaml.SafeLoader`, :class:`yaml.Loader`, :class:`yaml.UnsafeLoader`
        One of the :module:`yaml` loader
    node: :class:`yaml.nodes`
        Some YAML node to process

    Returns
    -------
    str
        YAML node value where environment variables have been replaced by their values
    """
    value = node.value
    match = _osenv_matcher.match(value)
    env_var = match.group()[2:-1]
    return os.environ.get(env_var) + value[match.end() :]


# Register the new tag to be identified:
yaml.add_implicit_resolver("!osenv", _osenv_matcher, None, yaml.SafeLoader)

# Register how to handle all "!osenv" objects:
yaml.add_constructor("!osenv", osenv_constructor, yaml.SafeLoader)


def load_config_from_file(fname: str | Path) -> dict[str, Any]:
    """Load a Pydox configuration file

    All environmental variables will be replaced by their values automatically.

    Parameters
    ----------
    fname: str, Path
        File name to load, must be YAML and encoded as utf-8

    Returns
    -------
    dict[str, Any]
        The configuration set of parameters
    """
    with open(Path(fname), "r") as f:
        cfg = yaml.load(f, Loader=yaml.SafeLoader)
    return cfg
