"""A bunch of custom errors used in pydox"""

from typing import Optional


class MissingSetting(ValueError):
    """Raise for missing setting in the configuration"""

    pass


class UnsupportedSetting(ValueError):
    """Raise when a setting is given a value that is not supported because of a missing implementation"""

    pass


class UnFitted(ValueError):
    """Raise when trying to work with a Workflow instance that is not fitted but must be"""

    def __init__(self, txt: Optional[str] = None):
        self.txt = "This instance is not fitted yet" if txt is None else txt

    def __str__(self):
        """Print error."""
        return repr(self.txt)


class UnSelected(ValueError):
    """Raise when trying to access 'best_fit' before using 'set_best_fit'"""

    pass
