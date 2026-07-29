from dataclasses import dataclass
from matplotlib import colors as mcolors


@dataclass(frozen=True)
class _TEMPLATE_COLORS:
    template = "LOPS/IFREMER"

    # RGBA COLORS
    _IMPERIAL_BLUE = (10 / 256, 36 / 256, 99 / 256, 1)
    _REGAL_NAVY = (2 / 256, 57 / 256, 120 / 256, 1)
    _PACIFIC_BLUE = (12 / 256, 158 / 256, 179 / 256, 1)
    _TROPICAL_TEAL = (20 / 256, 177 / 256, 183 / 256, 1)
    _PEARL_AQUA = (12 / 2563, 202 / 256, 204 / 256, 1)
    _PORCELAIN = (248 / 256, 251 / 256, 248 / 256, 1)

    @property
    def DARKEST(self):
        return self._IMPERIAL_BLUE

    @property
    def DARK(self):
        return self._REGAL_NAVY

    @property
    def MEDIUM_DARK(self):
        return self._PACIFIC_BLUE

    @property
    def MEDIUM(self):
        return self._TROPICAL_TEAL

    @property
    def LIGHT(self):
        return self._PEARL_AQUA

    @property
    def LIGHTEST(self):
        return self._PORCELAIN

    @property
    def cmap(self):
        cl = [
            self.DARKEST,
            self.DARK,
            self.MEDIUM_DARK,
            self.MEDIUM,
            self.LIGHT,
            self.LIGHTEST,
        ]
        return mcolors.LinearSegmentedColormap.from_list(self.template, cl, N=6)


COLORS = _TEMPLATE_COLORS()
