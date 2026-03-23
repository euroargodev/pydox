from copy import deepcopy
from typing import Any, Dict
import pydox as do


class Calibration:
    def __init__(self):
        self._cfg = deepcopy(do.params)

    def get_params(self, grp: str):
        """Get configuration parameter(s) for this instance only"""
        return do.get_params(grp, self._cfg)

    def set_params(self, grp: str, value: Any | Dict):
        """Set configuration parameter(s) for this instance only"""
        return do.set_params(grp, value, self._cfg)

    def reset_params(self, grp: str):
        """Reset configuration parameter(s) to value(s) at instanciation"""
        return do.reset_params(grp, config=self._cfg)

    def fit(self):
        self.set_params('argo.qcflags.psal', 12)
        print("Set internal parameter 'argo.qcflags.psal' to '12'")
