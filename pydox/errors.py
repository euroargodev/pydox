"""A bunch of custom errors used in pydox"""


class MissingSetting(ValueError):
    """Raise for missing setting in the configuration"""

    pass


class UnsupportedSetting(ValueError):
    """Raise when a setting is given a value that is not supported because of a missing implementation"""

    pass
