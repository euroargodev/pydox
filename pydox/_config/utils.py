import random
from typing import Any, Dict, Optional
import json
from pathlib import Path
import importlib
import re
import warnings
import datetime

import pydox as do
from pydox._config import _read_only_dotted_params
from pydox.errors import MissingSetting

_path2static = Path(
    importlib.util.find_spec("pydox.static").submodule_search_locations[0]
)

initial_missing = object()


def reduce(function, iterable, /, initial=initial_missing):
    it = iter(iterable)
    if initial is initial_missing:
        value = next(it)
    else:
        value = initial
    for element in it:
        dotted_str = iterable[0 : iterable.index(element)]
        dotted_str.append(element)
        missing = f"The '{'.'.join(dotted_str)}' setting appears to be missing in this configuration object"
        if value is None or element not in value:
            raise MissingSetting(missing)
        else:
            value = function(value, element)
    return value


def uid(obj: Any):
    """Return a unique string for a given object on each call"""
    s = str(id(obj))
    return "".join(random.sample(s, len(s)))


def get_shell():  # pragma: no cover
    return get_ipython().__class__.__name__


def runner() -> str:
    """Return string name of the executing runner

    Returns
    -------
    'notebook', 'terminal', 'standard'
    """
    try:
        shell = get_shell()
        if shell == "ZMQInteractiveShell":
            return "notebook"  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return "terminal"  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return "standard"  # Probably standard Python interpreter


def format_value_txt(value: Any) -> str:
    """Format values appropriately for the output."""
    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, (int, float, bool)):
        return str(value)
    elif isinstance(value, list):
        return json.dumps(value)
    else:
        return str(value)


def dict_to_string(d: Dict[str, Any], level: int = 0, indent: int = 2) -> str:
    """Recursively convert a nested dictionary to a formatted string."""
    indent_str = " " * (level * indent)
    lines = []
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{indent_str}{key}:")
            lines.append(dict_to_string(value, level + 1, indent=indent))
        else:
            lines.append(f"{indent_str}{key}: {format_value_txt(value)}")
    return "\n".join(lines)


def format_value_html(value: Any) -> str:
    """Format values appropriately for HTML output."""
    if isinstance(value, str):
        return f'<span class="collapsible-dict-value-str">"{value}"</span>'
    elif isinstance(value, bool):
        return f'<span class="collapsible-dict-value-bool">{str(value).lower()}</span>'
    elif isinstance(value, (int, float)):
        return f'<span class="collapsible-dict-value-num">{value}</span>'
    elif isinstance(value, list):
        return f'<span class="collapsible-dict-value-list">{json.dumps(value)}</span>'

    return f'<span class="collapsible-dict-value-any">{value}</span>'


def config_repr_txt(config: Dict[str, Any], indent: int = 2) -> str:
    """Return a pure string representation of a configuration object, a collapsible nested dictionary

    Parameters
    ----------
    config : Dict[str, Any], default = None
        A configuration object to print.
    indent : int, optional
        Number of spaces for indentation (default is 2).

    Returns
    -------
    str
        A pretty-printed string representation of the configuration.
    """
    lines = ["<pydox.configuration>"]
    desc = dict_to_string(config, indent=indent)
    [lines.append(l) for l in desc.split("\n")]
    return "\n".join(lines)


def config_repr_html(
    config: Dict[str, Any],
    collapsed: bool = True,
    with_keys: bool = False,
    css_path: str = _path2static.joinpath("style.css"),
    tidy: bool = True,
) -> str:
    """Render an HTML string representation of a configuration object, a collapsible nested dictionary

    Uses only HTML and CSS (no JavaScript).

    Parameters
    ----------
    config : Dict[str, Any], default = None
        A configuration object to render.
    collapsed: bool, default = True
        Initial state for group of parameters, should they be collapsed or not
    with_keys: bool, default = False
        Display string-dotted syntax for each parameter.

    Other Parameters
    ----------------
    css: str | Path, optional
        Custom CSS stylesheet to user
    tidy: bool, default=True
        Should we _compress_ the CSS and HTML code or not.

    Returns
    -------
    str
        HTML string representation of the configuration. To be rendered with IPython.display.HTML
    """

    def clean_css(css) -> str:
        # Remove new lines and blank spaces:
        css = css.replace("\n", "").replace(" ", "")
        # Remove block comments (/* ... */):
        cleaned = []
        i = 0
        while i < len(css):
            if css[i : i + 2] == "/*":
                # Skip until the end of the comment
                i = css.find("*/", i) + 2
                if i == 1:  # No closing delimiter found
                    i = len(css)
            else:
                cleaned.append(css[i])
                i += 1
        return "".join(cleaned)

    def clean_html(html_string):
        """
        Remove blank lines and unnecessary whitespace between HTML tags.

        Args:
            html_string (str): The HTML string to clean.

        Returns:
            str: The cleaned HTML string with no blank lines or excessive whitespace.
        """
        # Remove blank lines
        html_string = re.sub(r"\n\s*\n", "\n", html_string)

        # Remove leading/trailing whitespace from each line
        html_string = "\n".join(line.strip() for line in html_string.split("\n"))

        # Remove whitespace between tags (but preserve whitespace inside tags)
        html_string = re.sub(r">\s+<", "><", html_string)

        # Remove any remaining empty lines
        html_string = "\n".join(
            line for line in html_string.split("\n") if line.strip()
        )

        return html_string

    def dict_to_html(d: dict[str, Any], level=0, upper_key="") -> str:
        items_html = []
        for key, value in d.items():
            abs_key = f"{key}" if upper_key == "" else f"{upper_key}.{key}"
            if key in _read_only_dotted_params:
                key_status = "read-only-key"
            else:
                key_status = "regular-key"

            if isinstance(value, dict):
                # Generate a unique ID for the checkbox and label
                checkbox_id = f"{uid(d)}-checkbox-{key}-{level}"

                # Then the HTML:
                value_html = f"""
                <input type="checkbox" id="{checkbox_id}" class="collapsible-dict-input" {checked}>
                <label for="{checkbox_id}" class="collapsible-dict-label">{key}</label>
                <div class="collapsible-dict-value">
                    {dict_to_html(value, level + 1, upper_key=abs_key)}
                </div>
                """
            else:
                if with_keys:
                    value_html = f"""
                    <div class="collapsible-dict-key-value">
                        <div class="collapsible-dict-key {key_status}"><span class="tooltiptext">{abs_key}:</span></div>                    
                        <div class="collapsible-dict-simple-value">{format_value_html(value)}</div>
                    </div>
                    """
                else:
                    value_html = f"""
                    <div class="collapsible-dict-key-value">
                        <div class="collapsible-dict-key {key_status}">{key}:</div>                    
                        <div class="collapsible-dict-simple-value">{format_value_html(value)}</div>
                    </div>
                    """
            # <div class="collapsible-dict-item" style="margin-left: {5 * level}px;">
            items_html.append(
                f"""
            <div class="collapsible-dict-item lm-{level}">
                {value_html}
            </div>
            """
            )
        return "\n".join(items_html)

    css_style = Path(css_path).resolve().read_text(encoding="utf-8")
    if tidy:
        css_style = clean_css(css_style)

    checked = "" if collapsed else "checked"  # Initial state: All collapsed or expanded
    html = f"""
    <div>
        <style>{css_style}</style>
        <div class='do-warp'>
          <div class='do-header'>pydox Configuration</div>
            <div class="collapsible-dict-container">
                {dict_to_html(config)}
            </div>
          </div>
        </div>
    </div>
    """
    if tidy:
        return clean_html(html)

    return html


def list_methods() -> list[str]:
    """Return the list of calibration methods, as described in the configuration"""
    methods = []
    for key in do.get_params("calibration_methods"):
        if key != "default":
            methods.append(key)
    return methods


def tmp_root(new: bool = False, config: Optional[object] = None) -> Path:
    """Return a temporary folder path



    Parameters
    ----------
    new: bool, default = False
        Force create a new temporary folder on each call.
    config: Config, default = None
        The configuration object to read the ``output.root`` parameter from.
        If set to None (default), we use the runtime configuration object.

    Returns
    -------
    :class:`pathlib.Path`

    Notes
    -----
    The temporary folder is named after the exact creation datetime stamp, following the general format:

    ``<output.root>/tmp/<%Y%m%d%H%M%S%f>``

    Eg: If ``output.root`` is set to: ``/Users/johndoe/pydox``
    then the temporary folder is something like: ``/Users/johndoe/pydox/tmp/20260717100903168376``.

    Note that if the ``output.root`` configuration parameter is not set, we fall back on the current working directory.

    Also note that a unique temporary folder is created at runtime, therefore, calling ``do.tmp_root()`` twice will return the same result.

    In order to force create a new temporary folder, use the argument ``new=True``.

    """
    from pydox._config.config import check_config  # Avoid circular import

    config = do.params if config is None else check_config(config)

    try:
        tmp_name = do.get_params("output._tmp")
    except:
        tmp_name = None

    if new or tmp_name is None:
        # This is the 1st call, we create a new folder:

        root = do.get_params("output.root", config)
        if root is None:
            warnings.warn(
                "The Pydox output root path is not set, fallback on current directory"
            )
            root = Path.cwd()
        root = Path(root)

        # tmp_root = root.joinpath("tmp").joinpath(uuid.uuid4().hex)
        tmp = root.joinpath("tmp").joinpath(
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f")
        )

        # Register folder in the configuration, as a private parameter
        do.set_params("output._tmp", str(tmp), config=config)

    # Read the corresponding parameter:
    tmp = Path(do.get_params("output._tmp", config))

    # Make sure the folder exists even if it was deleted between the creation time and call to this function:
    tmp.mkdir(parents=True, exist_ok=True)

    return tmp
