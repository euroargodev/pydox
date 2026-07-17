"""
Commodity classes

These are objects used as interface between high-level APIs (eg: `Calibration`) and low-level computational functions (eg: `inair_fit`).

Most commodity classes have a _frozen_ state:

Frozen == attributes must be set at instanciation, not later, ie instances are read-only

We also define custom types

Notes
-----
> If your object needs significant logic to be valid, hiding that logic in __post_init__ is rarely the best design.
> If the class has no real behavior, @dataclass is perfect.
https://medium.com/the-pythonworld/why-i-stopped-using-python-dataclass-everywhere-3d0cc5457e01
"""

import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
import numpy as np
from typing import (
    Any,
    Union,
    Dict,
    Optional,
    TypeAlias,
    OrderedDict,
    Protocol,
    runtime_checkable,
    Callable,
    Self,
)
import matplotlib as mpl
import pickle


@dataclass(frozen=1)
class Data:
    """A placeholder for a numerical item: store a value and an error, as float32"""

    value: Union[float, int, np.number]
    error: Union[float, int, np.number] = field(default_factory=lambda: 0.0)

    def __post_init__(self):
        # Re-enforce data types
        object.__setattr__(self, "value", np.float32(self.value))
        object.__setattr__(self, "error", np.float32(self.error))

    def __str__(self) -> str:
        # The machine precision for float32 is about 7 digits
        return f"{self.value:.7} (err={self.error:.7})"


@runtime_checkable
class ParameterSet(Protocol):
    """Define a type for a unique collection of parameters describing a single computation of coefficients

    Notes
    -----
    - This protocol allows to define types wherever instances of Params, ParamsInAir, ParamsClimatology are expected
    - We set in here what is expected from any implementation, on our case, this will be the Params class and its children ParamsInAir, ParamsClimatology.
    """

    fit_drift: bool
    initial_gain: Data
    initial_drift: Data
    cycles: Any  # not sure what to use exactly here

    @property
    def uid(self) -> str: ...


ConfigsDict: TypeAlias = OrderedDict[int, ParameterSet]
"""A type for the Workflow.configs attribute, hence for Workflow.flatten_configs() and Workflow._flatten_configs() methods output"""


@dataclass(frozen=True)
class Params:
    """A dataclass to hold a unique parameter set for one computation

    This class produces instances that type as `ParameterSet`.

    Notes
    -----
    - These parameters are from any group of the configuration, but shared by ALL methods
    - Each parameter has a unique value, even if a list is supplied in the configuration
    - Instance of `Params` are expected to be produced by Workflow._flatten_configs() and to fill values of a `ConfigsDict` type.
    - There is no reason to do not have parameters from outside the configuration
    - Create children to be specific about one method parameters
    """

    fit_drift: bool
    initial_gain: Data
    initial_drift: Data
    cycles: Any  # not sure what to use exactly here
    dummy: int  # For dev. only

    @property
    def uid(self) -> str:
        """Return a unique string to identify this set of parameters"""
        return f"{int(self.fit_drift)}-{id(self.initial_gain)}-{id(self.initial_drift)}"


@dataclass(frozen=True)
class ParamsInAir(Params):
    """A unique parameter set for the 'in air' method

    Notes
    -----
    - These parameters are from the 'calibration_methods.in_air' subgroup of the configuration
    - There is no reason to expect all parameters from this subgroup to be attributes of this class
    - Each parameter has a unique value, even if a list is supplied in the configuration
    """

    carryover: bool
    dataset: str
    src: str
    initial_carryover: Data = field(default_factory=lambda: Data(0.0, 0.0))
    method: str = field(default="in_air", init=False)

    @property
    def uid(self) -> str:
        """Return a unique string to identify this set of parameters"""
        return f"{super().uid}-{self.method}-{int(self.carryover)}-{self.dataset}"


@dataclass(frozen=True)
class ParamsClimatology(Params):
    """A unique parameter set for the 'climatology' method

    Notes
    -----
    - These parameters are from the 'calibration_methods.climatology' subgroup of the configuration
    - There is no reason to expect all parameters from this subgroup to be attributes of this class
    - Each parameter has a unique value, even if a list is supplied in the configuration
    """

    min_pressure: float
    max_pressure: float
    dataset: str
    src: str
    method: str = field(default="climatology", init=False)

    @property
    def uid(self) -> str:
        """Return a unique string to identify this set of parameters"""
        return f"{super().uid}-{self.method}-{int(self.min_pressure)}-{int(self.max_pressure)}-{self.dataset}"


class PostInitCaller(type):
    """A metaclass allowing to implement a __post_init__

    __post_init__ is primarily used to freeze an instance
    """

    def __call__(cls, *args, **kwargs):
        obj = type.__call__(cls, *args, **kwargs)
        obj.__post_init__(*args, **kwargs)
        return obj


# We don't use a dataclass to handle data validation, a custom frozen state and print outputs
class Coefficients(metaclass=PostInitCaller):
    """Maybe some placeholder for coefficients results"""

    _frozen: bool = False

    def __init__(self, gain: Data, drift: Optional[Data] = None, **kwargs):
        """

        Parameters
        ----------
        gain : Data
        drift : Optional[Data]
        """
        if gain is None:
            raise ValueError(f"You must at least provide a :class:`Data` for the gain")
        elif not isinstance(gain, Data):
            raise ValueError(f"'gain' must be a :class:`Data` instance")
        else:
            self.gain: Data = gain

        if drift is not None and not isinstance(drift, Data):
            raise ValueError(f"'drift' must be a :class:`Data` instance")
        else:
            self.drift: Data = drift

    def __post_init__(self, *args, **kwargs) -> None:
        # this method is called at the end of __init__, thanks to the metaclass PostInitCaller
        self._frozen = True if kwargs.get("frozen", True) is True else False

    def __setattr__(self, attr, value):
        if getattr(self, "_frozen", None):
            raise AttributeError("Trying to set attribute on a frozen instance")
        return super().__setattr__(attr, value)

    def __str__(self):
        msg = f"gain={str(self.gain)}"
        if self.drift is not None:
            msg += f", drift={str(self.drift)}"
        return msg

    def __repr__(self):
        msg = f"{self.__class__.__name__}(gain={self.gain}"
        if self.drift is not None:
            msg += f", drift={self.drift}"
        msg += ")"
        return msg

    def to_dict(self) -> Dict[str, Any]:
        d = {"gain": asdict(self.gain)}
        if self.drift is not None:
            d["drift"] = asdict(self.drift)
        return d


class CoefficientsInAir(Coefficients):
    """Maybe some placeholder for coefficients results from the in-air method"""

    def __init__(self, carryover: Optional[Data] = None, **kwargs):
        super().__init__(**{**kwargs, **{"frozen": False}})
        # frozen=False ensures we can set more attributes in this init, but this will be set to True in a postinit

        if carryover is not None and not isinstance(carryover, Data):
            raise ValueError(f"'carryover' must be a :class:`Data` instance")
        else:
            self.carryover: Data = carryover

    def __str__(self):
        msg = super().__str__()
        if self.carryover is not None:
            msg += f", carryover={str(self.carryover)}"
        return msg

    def __repr__(self):
        msg = super().__repr__()[0:-1]
        if self.carryover is not None:
            msg += f", carryover={self.carryover}"
        msg += ")"
        return msg

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        if self.carryover is not None:
            d["carryover"] = asdict(self.carryover)
        return d


CoefsDict: TypeAlias = OrderedDict[int, Coefficients | CoefficientsInAir]
"""A type for a dictionary of fit coefficients"""


@dataclass(frozen=True)
class FitResult:
    """Maybe some placeholder for a single fit result"""

    coefs: Coefficients | CoefficientsInAir
    fit_data: dict[str, Any]


FitResults: TypeAlias = OrderedDict[int, FitResult]
"""A type for a dictionary of a single fit result, e.g. from core.in_air.fit(). Holds and instance of Coefficients and input fit data"""

VALID_FIGURE_CATEGORIES = ["debug", "input_data", "fit_results"]


@dataclass
class PydoxFigure:

    fig: mpl.figure.Figure
    name: str
    category: str = None
    config_uid: str = None
    caller: Callable | str = None
    pickle: Path = None
    # axes: mpl.axes._axes.Axes | list[mpl.axes._axes.Axes] = None

    def __post_init__(self):
        # Validate/set the category
        if self.category is not None:
            if self.category not in VALID_FIGURE_CATEGORIES:
                raise ValueError(
                    f"'{self.category}' is not a valid category. Must be one in: {VALID_FIGURE_CATEGORIES}"
                )
        else:
            # Set to default category (lowest level):
            object.__setattr__(self, "category", "debug")

    @property
    def level(self) -> int:
        cat2level = {
            "debug": 0,
            "input_data": 1,
            "fit_results": 2,
        }
        return cat2level[self.category]

    @property
    def uid(self) -> str:
        m = hashlib.sha256()
        m.update(bytes(str(self.name), "utf-8"))
        if self.config_uid is not None:
            m.update(bytes(str(self.config_uid), "utf-8"))
        if self.caller is not None:
            m.update(bytes(str(self.caller), "utf-8"))
        return m.hexdigest()

    def reload(self) -> Self:
        with open(self.pickle, "rb") as fid:
            self.fig = pickle.load(fid)
        return self

    def show(self):
        self.fig.show()


@dataclass
class PlotParams:
    """A placeholder for plotting parameters to be communicated from high to low-level APIs"""

    level: int = None
    uid: str = None
    watermark: str = None
    dpi: int = 90
