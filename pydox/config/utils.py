import random
from typing import Any, Dict
import json
from pathlib import Path


def uid(obj: Any):
    s = str(id(obj))
    return "".join(random.sample(s, len(s)))


def runner() -> str:
    """Return string name of the executing runner

    Returns
    -------
    'notebook', 'terminal', 'standard'
    """
    try:
        shell = get_ipython().__class__.__name__
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


def format_value_html(value: Any) -> str:
    """Format values appropriately for HTML output."""
    if isinstance(value, str):
        return f'<span class="collapsible-dict-value-str">"{value}"</span>'
    elif isinstance(value, (int, float)):
        return f'<span class="collapsible-dict-value-num">{value}</span>'
    elif isinstance(value, bool):
        return f'<span class="collapsible-dict-value-bool">{str(value).lower()}</span>'
    elif isinstance(value, list):
        return f'<span class="collapsible-dict-value-list">{json.dumps(value)}</span>'
    else:
        return str(value)


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

    def dict_to_string(d: Dict[str, Any], level: int = 0) -> str:
        """Recursively convert a nested dictionary to a formatted string."""
        indent_str = " " * (level * indent)
        lines = []
        for key, value in d.items():
            if isinstance(value, dict):
                lines.append(f"{indent_str}{key}:")
                lines.append(dict_to_string(value, level + 1))
            else:
                lines.append(f"{indent_str}{key}: {format_value_txt(value)}")
        return lines

    lines = ["<pydox.configuration>"]
    [lines.append(l) for l in dict_to_string(config)]
    return "\n".join(lines)


def config_repr_html(
    config: Dict[str, Any],
    css_path: str = "static/style.css",
) -> str:
    """Render an HTML string representation of a configuration object, a collapsible nested dictionary

    Keys and values are displayed on the same line for non-dict values.
    Uses only HTML and CSS (no JavaScript).

    Parameters
    ----------
    config : Dict[str, Any], default = None
        A configuration object to render.
    css: str | Path
        Path toward the css stylesheet to apply

    Returns
    -------
    str
        A html string representation of the configuration. To be rendered with IPython.display.HTML
    """

    def dict_to_html(d, level=0):
        items_html = []
        for key, value in d.items():
            if isinstance(value, dict):
                # Generate a unique ID for the checkbox and label
                checkbox_id = f"{uid(d)}-checkbox-{key}-{level}"
                value_html = f"""
                <input type="checkbox" id="{checkbox_id}" class="collapsible-dict-input">
                <label for="{checkbox_id}" class="collapsible-dict-label">{key}</label>
                <div class="collapsible-dict-value">
                    {dict_to_html(value, level + 1)}
                </div>
                """
            else:
                value_html = f"""
                <div class="collapsible-dict-key-value">
                    <div class="collapsible-dict-key">{key}:</div>
                    <div class="collapsible-dict-simple-value">{format_value_html(value)}</div>
                </div>
                """
            items_html.append(
                f"""
            <div class="collapsible-dict-item" style="margin-left: {5 * level}px;">
                {value_html}
            </div>
            """
            )
        return "\n".join(items_html)

    html = f"""
    <link rel="stylesheet" href="{Path(css_path).resolve()}">
    <div class='do-warp'>
      <div class='do-header'>pydox.Configuration</div>
        <div class="collapsible-dict-container">
            {dict_to_html(config)}
        </div>
      </div>
    </div>
    """
    return html
