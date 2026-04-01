"""

> If your object needs significant logic to be valid, hiding that logic in __post_init__ is rarely the best design.
> If the class has no real behavior, @dataclass is perfect.
https://medium.com/the-pythonworld/why-i-stopped-using-python-dataclass-everywhere-3d0cc5457e01
"""

from dataclasses import dataclass, field
from typing import Any

@dataclass
class Data:
    value: float
    error: float


@dataclass
class ParamsShared:
    """A dataclass to hold a parameter set for one computation
    Define parameters shared by all methods

    Notes
    -----
    - These parameters are from the 'calibration_parameters' group of the configuration
    - There is no reason to expect all parameters from this group
    - There is no reason do not have more parameters
    """

    fit_drift: bool
    initial_gain: Data
    initial_drift: Data

    @property
    def uid(self)-> str:
        """Return a unique string to identify this set of parameters"""
        return f"{int(self.fit_drift)}-{id(self.initial_gain)}-{id(self.initial_drift)}"


@dataclass
class ParamsInAir(ParamsShared):
    """A unique parameter set for the 'in air' method

    Notes
    -----
    - These parameters are from the 'calibration_methods.in_air' subgroup of the configuration
    - There is no reason to expect all parameters from this subgroup
    - There is no reason do not have more parameters
    """

    carryover: bool
    dataset: str
    src: str
    initial_carryover: Data = field(default_factory=lambda: Data(0., 0.))
    method: str = field(default="in_air", init=False)

    @property
    def uid(self)-> str:
        """Return a unique string to identify this set of parameters"""
        return f"{super().uid}-{self.method}-{int(self.carryover)}-{self.dataset}"


@dataclass
class ParamsClimatology(ParamsShared):
    """A unique parameter set for the 'climatology' method

    Notes
    -----
    - These parameters are from the 'calibration_methods.climatology' subgroup of the configuration
    - There is no reason to expect all parameters from this subgroup
    - There is no reason do not have more parameters
    """

    min_pressure: float
    max_pressure: float
    dataset: str
    src: str
    method: str = field(default="climatology", init=False)

    @property
    def uid(self)-> str:
        """Return a unique string to identify this set of parameters"""
        return f"{super().uid}-{self.method}-{int(self.min_pressure)}-{int(self.max_pressure)}-{self.dataset}"


@dataclass
class Coefficients:
    """Maybe some placeholder for coefficients results"""
    gain: Data = field(default_factory=lambda: Data(0., 0.))

@dataclass
class CoefficientsInAir:
    """Maybe some placeholder for coefficients results"""
    gain: Data = field(default_factory=lambda: Data(0., 0.))
    drift: Data = field(default_factory=lambda: Data(0., 0.))
    carryover: Data = field(default_factory=lambda: Data(0., 0.))

@dataclass
class FitResults:
    """Maybe some placeholder for a single fit result"""
    coefs: Coefficients | CoefficientsInAir
    fit_data: Any
