"""
The 'reporting' sub-module is to be understood in a general sense, i.e.:
- this module is not limited to the 'report' class to generate reporting documents
- this module includes logging management (for users and dev.)
- this module includes templating management (eg: config settings, color schemes, jinja templates, ...)

This may need to be more finely refactored in the future.

"""

from typing import Optional, Dict, Any
from pydox.reporting import colors
from pydox.reporting import logs
from pydox.reporting import pdf

COLORS: Optional[colors.ColorScheme] = None
MPLSTYLE: Optional[Dict[str, Any]] = None
