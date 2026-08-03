from matplotlib import colors as mcolors
import pydox as do


class Template2Colors:
    N: int = 7
    NAME: str = ""
    SCHEME: tuple[str] = []

    def __init__(self, scheme: list[str], name: str = ""):
        self.NAME = name
        self.SCHEME = scheme
        if len(self.SCHEME) != 7:
            raise ValueError(f"The template color scheme must have {self.N} colors")

    @classmethod
    def from_config(cls, config):
        return cls(
            scheme=do.get_params("reports.template.colors.scheme", config=config),
            name=do.get_params("reports.template.name", config=config),
        )

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
