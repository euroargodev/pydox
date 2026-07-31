from dataclasses import dataclass
from matplotlib import colors as mcolors


@dataclass(frozen=True)
class DEFAULT_SCHEME:
    NAME = "DEFAULT/PYDOX"

    # HEX COLORS
    _IMPERIAL_BLUE = "#0a2463ff"
    _REGAL_NAVY = "#023978ff"
    _PACIFIC_BLUE = "#0c9eb3ff"
    _TROPICAL_TEAL = "#14b1b7ff"
    _PEARL_AQUA = "#7bcaccff"
    _FROZEN_WATER = "#bae3e2ff"
    _PORCELAIN = "#f8fbf8ff"

    SCHEME = [
        _IMPERIAL_BLUE,
        _REGAL_NAVY,
        _PACIFIC_BLUE,
        _TROPICAL_TEAL,
        _PEARL_AQUA,
        _FROZEN_WATER,
        _PORCELAIN,
    ]


class Template2Colors:
    N: int = 7
    NAME: str = ""
    SCHEME: tuple[str] = []

    def __init__(self, scheme):
        self.NAME = scheme.NAME
        self.SCHEME = scheme.SCHEME
        if len(self.SCHEME) != 7:
            raise ValueError(f"The template color scheme must have {self.N} colors")

    @classmethod
    def from_scheme(cls, scheme):
        return cls(scheme)

    def convert(self, hex: str):
        return mcolors.to_rgba(hex)

    @property
    def DARKEST(self):
        return self.convert(self.SCHEME[0])

    @property
    def DARK(self):
        return self.convert(self.SCHEME[1])

    @property
    def MEDIUM_DARK(self):
        return self.convert(self.SCHEME[2])

    @property
    def MEDIUM(self):
        return self.convert(self.SCHEME[3])

    @property
    def LIGHT_MEDIUM(self):
        return self.convert(self.SCHEME[4])

    @property
    def LIGHT(self):
        return self.convert(self.SCHEME[5])

    @property
    def LIGHTEST(self):
        return self.convert(self.SCHEME[6])

    @property
    def cmap(self):
        return mcolors.LinearSegmentedColormap.from_list(
            self.NAME, self.SCHEME, N=self.N
        )


COLORS = Template2Colors.from_scheme(DEFAULT_SCHEME)
