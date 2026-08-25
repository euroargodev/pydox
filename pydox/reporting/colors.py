from typing import TypeAlias, Optional, Any
from matplotlib import colors as mcolors
import pydox as do

Color: TypeAlias = tuple[float, float, float, float]  # RGBA


class ColorScheme:
    """A class handler for the color scheme defined in the configuration setting "reports.template.colors"

    Examples
    --------
    This class is expected to be instantiated from a configuration object like this:

    ..code-block::python

        import pydox as do
        cs = do.reporting.ColorScheme.from_config(do.params)

    From the color scheme, all 7 colors are accessible with attributes:

    ..code-block::python

        cs.DARKEST
        cs.DARK
        cs.MEDIUM_DARK
        cs.MEDIUM
        cs.LIGHT_MEDIUM
        cs.LIGHT
        cs.LIGHTEST

    And the colormap for use with Matplotlib with the cmap attribute:

    ..code-block::python

        cs.cmap

    """

    N: int = 7
    NAME: str = ""
    SCHEME: tuple[str] = []  # HEX color scheme
    _KEYS: list[str] = [
        "DARKEST",
        "DARK",
        "MEDIUM_DARK",
        "MEDIUM",
        "LIGHT_MEDIUM",
        "LIGHT",
        "LIGHTEST",
    ]

    def __init__(self, scheme: list[str], name: str = ""):
        """A class handler for the color scheme defined in the configuration setting "reports.template.colors.scheme"

        Parameters
        ----------
        scheme: list[str]
        name: str

        Examples
        --------
        This class is expected to be instantiated from a configuration object like this:

        ..code-block::python

            import pydox as do
            cs = do.reporting.ColorScheme.from_config(do.params)

        From the color scheme, all 7 colors are accessible with attributes:

        ..code-block::python

            cs.DARKEST
            cs.DARK
            cs.MEDIUM_DARK
            cs.MEDIUM
            cs.LIGHT_MEDIUM
            cs.LIGHT
            cs.LIGHTEST

        And the colormap for use with Matplotlib with the cmap attribute:

        ..code-block::python

            cs.cmap

        """
        self.NAME = name
        self.SCHEME = scheme
        if len(self.SCHEME) != 7:
            raise ValueError(f"The template color scheme must have {self.N} colors")

    @classmethod
    def from_config(cls, config: Optional[Any] = None) -> "ColorScheme":
        """Create a :class:`ColorScheme` from a configuration object"""
        if do.get_params("reports.template", config=config).get(
            "colors", None
        ) and do.get_params("reports.template", config=config).get("name", None):
            return cls(
                scheme=do.get_params("reports.template.colors", config=config),
                name=do.get_params("reports.template.name", config=config),
            )
        else:
            raise ValueError(
                "Settings 'reports.template.colors' and/or 'reports.template.name' are missing from this configuration object to create a color scheme."
            )

    def _convert(self, hex: str) -> Color:
        """Private color format converter

        This method converts template HEX color strings to RGBA floats.

        Return a tuple of floats ``(r, g, b, a)``, where each channel (red, green, blue,
        alpha) can assume values between 0 and 1"""
        return mcolors.to_rgba(hex)

    @property
    def DARKEST(self) -> Color:
        return self._convert(self.SCHEME[0])

    @property
    def DARK(self) -> Color:
        return self._convert(self.SCHEME[1])

    @property
    def MEDIUM_DARK(self) -> Color:
        return self._convert(self.SCHEME[2])

    @property
    def MEDIUM(self) -> Color:
        return self._convert(self.SCHEME[3])

    @property
    def LIGHT_MEDIUM(self) -> Color:
        return self._convert(self.SCHEME[4])

    @property
    def LIGHT(self) -> Color:
        return self._convert(self.SCHEME[5])

    @property
    def LIGHTEST(self) -> Color:
        return self._convert(self.SCHEME[6])

    @property
    def cmap(self) -> mcolors.LinearSegmentedColormap:
        return mcolors.LinearSegmentedColormap.from_list(
            self.NAME, self.SCHEME, N=self.N
        )
