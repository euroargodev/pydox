from copy import deepcopy
import pydox as do


class Calibration:
    def __init__(self):
        self._cfg = deepcopy(do.params)

    def get_params(self, *args, **kwargs):
        """Get configuration parameter(s) for this instance only"""
        return do.get_params(*args, **kwargs, config=self._cfg)

    def set_params(self, *args, **kwargs):
        """Set configuration parameter(s) for this instance only"""
        return do.set_params(*args, **kwargs, config=self._cfg)

    def reset_params(self, *args, **kwargs):
        """Reset configuration parameter(s) to instanciation initial value(s)

        ‼️ This method does not reset parameters to current _default_ or _factory_ values, but to values at instanciation time.
        """
        return do.reset_params(*args, **kwargs, config=self._cfg)

    def fit(self):
        """Some dummy method that will modify this instance parameters"""
        self.set_params('argo.qcflags.psal', 12)
        print("Set internal parameter 'argo.qcflags.psal' to '12'")
