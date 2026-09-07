_valid_config_version = "0.1"

# List of parameters (group, subgroup, key) that are read-only,
# (i.e. cannot be modified with ``do.set_params``):
_read_only_dotted_params = [
    "version",
    "specification",
]  # use lower-dotted string format

# List of parameters (group, subgroup, key) that are NOT over-writen when loading the sequence of config. files,
# (i.e. factory values are read-only):
_not_overloaded_dotted_params = [
    "version",
    "output._tmp",
]  # use lower-dotted string format
