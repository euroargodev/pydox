"""
Commodity classes and Figures registry manager

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
from functools import partial
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
        # Validate/set
        if not isinstance(self.fig, mpl.figure.Figure):
            raise ValueError(
                f"Cannot create a PydoxFigure. 'fig' must be a matplotlib.figure.Figure instance, get {type(self.fig)} instead."
            )

        if self.category is not None:
            if self.category not in VALID_FIGURE_CATEGORIES:
                raise ValueError(
                    f"Cannot create a PydoxFigure. '{self.category}' is not a valid category. Must be one in: {VALID_FIGURE_CATEGORIES}"
                )
        else:
            # Set to default category (lowest level):
            object.__setattr__(self, "category", "debug")

    @property
    def level(self) -> int:
        """This figure level based on its category attribute"""
        cat2level = {
            "debug": 0,
            "input_data": 10,
            "fit_results": 20,
        }
        return cat2level[self.category]

    @property
    def uid(self) -> str:
        """This instance uid, not to be confused with 'config_uid'"""
        m = hashlib.sha256()
        m.update(bytes(str(self.name), "utf-8"))
        if self.config_uid is not None:
            m.update(bytes(str(self.config_uid), "utf-8"))
        if self.caller is not None:
            m.update(bytes(str(self.caller), "utf-8"))
        return m.hexdigest()

    def reload(self) -> Self:
        """Reload the pickle file with this figure object, and update the 'fig' attribute"""
        with open(self.pickle, "rb") as fid:
            self.fig = pickle.load(fid)
        return self

    def show(self):
        """Call :meth:`mpl.figure.Figure.show` on this instance figure object."""
        self.fig.show()


class _DoFigures:
    """Provide a facade to the internal global registry of figures

    This is not intended to be called directly by end-users.

    Use `do.figures` instead.
    """

    def __init__(self, obj):
        self.registry: list[PydoxFigure] = (
            obj  # no copy ! just the pointer to stay in sync with the global registry do.__figures.
        )

    def __getitem__(self, *args) -> list[PydoxFigure] | PydoxFigure:
        """Get a :class:`PydoxFigure` instance from global registry

        Use figure index or figure name indexing
        """
        if isinstance(args[0], str):
            return [fig for fig in self.registry if fig.name == args[0]]
        else:
            return self.registry.__getitem__(*args)

    def __len__(self) -> int:
        return len(self.registry)

    def __iter__(self):
        for v in self.registry:
            yield v

    def __repr__(self) -> str:
        summary = ["<pydox.figures>"]
        summary.append(f"{len(self)} figures commited:")

        cat_width = max([len(f.category) for f in self] + [10])
        name_width = max([len(f.name) for f in self] + [10])
        uid_width = max(
            [len(f.config_uid) for f in self if f.config_uid is not None] + [10]
        )

        for fig in self:
            msg = f"| {fig.level:2d} | {fig.category:{cat_width}} | {fig.name:{name_width}}"
            if fig.config_uid == "" or fig.config_uid is None:
                uid_msg = "orpheans 😵"
            else:
                uid_msg = fig.config_uid
            msg = f"{msg} | {uid_msg:{uid_width}} |"

            summary.append(msg)
        return "\n".join(summary)

    def _ipython_key_completions_(self) -> list[str]:
        """Provide method for key-autocompletions in IPython."""
        return [p.name for p in self]

    def commit(
        self,
        fig: mpl.figure.Figure,
        name: str,
        category: Optional[str] = None,
        watermark: Optional[str] = None,
        config_uid: Optional[str] = None,
        dest: Optional[Path] = None,
    ):
        """Commit a named :mpl:`Figure` object to the global registry of figures

        This function is to be called from anywhere in the library.

        A commit is the following set of operations:
        - create a new :class:`do.PydoxFigure` instance and append it to the global registry if not already there,
        - print a watermark on each axes of the figure (if `plots.watermark.show` is set to True),
        - save the :mpl:`Figure` object on a temporary pickle file,
        - close the :mpl:`Figure` object (show or save is managed elsewhere using the global registry).

        Use the registry to report/show figures matching some criteria based on meta-data filtering.

        Parameters
        ----------
        fig: :class:`mpl.figure.Figure`
            The :class:`mpl.figure.Figure` instance to commit.
        name: str
            The string name given to the figure.

        Other Parameters
        ----------------
        category: str, default=None
            The figure category to assign to this figure.
            Possible values are given in :obj:`do.commodities.VALID_FIGURE_CATEGORIES`.
        watermark: str, default = None
            If the `plots.watermark.show` setting is True, print this watermark on the figure.
            Note that the default watermark (from `plots.watermark.default` setting) is always added, even if this argument is None.
        config_uid: str, default=None
            The unique ID to associate this figure with.
            This is typically a configuration UID, as return by :meth:`Calibration.uid`.
        dest: Path, default=do.tmp_root()
            Destination folder of the figure pickle file.
            This is not the report output and this folder is likely temporary.
        """
        import pydox as do  # Avoid circularity

        if name.strip() == "" or name is None:
            raise ValueError("A figure must have a name to be commited")

        # Create a PydoxFigure instance with these figure and meta-data:
        this_f = PydoxFigure(
            fig=fig, name=name, category=category, config_uid=str(config_uid)
        )

        # Check, by uid, if the figure was already committed:
        found = False
        for f in self:
            if this_f.uid == f.uid:
                found = True

        # If not found, commit this:
        if not found:
            print(
                f"Commit figure '{this_f.name}' (level {this_f.level} / {this_f.category})"
            )

            # Print watermark:
            print_watermark: bool = do.get_params("plots.watermark.show")
            default_watermark: str = do.get_params("plots.watermark.default")

            if print_watermark and (
                watermark is not None or default_watermark is not None
            ):
                if default_watermark is not None:
                    if watermark is None:
                        watermark = default_watermark
                    else:
                        watermark = "\n".join([watermark, default_watermark])

                for ax in fig.axes:
                    ax.text(
                        0.5,
                        0.5,
                        watermark,
                        transform=ax.transAxes,
                        fontsize=40,
                        color="gray",
                        alpha=0.5,
                        ha="center",
                        va="center",
                        rotation=30,
                    )

            # Save figure object to a pickle file:
            dest = do.tmp_root() if dest is None else Path(dest)
            dest.mkdir(parents=True, exist_ok=True)
            pkl = dest.joinpath(f"{this_f.uid}.pkl")
            with open(pkl, "wb") as fid:
                pickle.dump(this_f.fig, fid)
            this_f.pickle = (
                pkl  # Update PydoxFigure path to the appropriate pickle file
            )

            # Add this PydoxFigure instance to the internal global registry:
            self.registry.append(this_f)

        # Close figure upon commit:
        # Showing is controlled by higher-level methods, such as Calibration.plot()
        mpl.pyplot.close(fig)

    @property
    def orpheans(self) -> list[PydoxFigure]:
        """List orphean figures

        A figure is considered as an _orphean_ if it has no 'config_uid'.
        """
        return [fig for fig in self if fig.config_uid == ""]

    def clear(self):
        """Clear global registry and delete pickle files

        If the parent folder of pickle files is left empty at the end of the process (and is not the internal temporary folder given by do.get_tmp()), we also delete it.
        """
        import pydox as do  # Avoid circularity

        # Delete files and registry entry (capture the list of parent folders as well).
        parents_folder = []
        while self.registry:
            fig = self.registry.pop(0)
            pick = Path(fig.pickle)
            parents_folder.append(pick.parents[0])
            pick.unlink(missing_ok=True)

        # Handle parent folders
        # Delete if empty (ignore .* hidden files)
        parents_folder = list(set(parents_folder))
        while parents_folder:
            par = parents_folder.pop(0)
            if par != do.tmp_root():
                content = [
                    child for child in par.iterdir() if not child.name.startswith(".")
                ]
                if len(content) == 0:
                    par.rmdir()

    def uidstartswith(self, uid: str) -> list[PydoxFigure]:
        return [
            fig
            for fig in self
            if fig.config_uid is not None and fig.config_uid.startswith(uid)
        ]

    def to_pdf(self, pdf_file: Path | str, **kwargs):
        from pydox.reporting.pdf import registry_report

        return registry_report(self.registry, outputfile=pdf_file, **kwargs)


@runtime_checkable
class TPlotParams(Protocol):
    """A type for anything able to return a PlotParams class instance

    This is used by functions with an argument that is either a partial of PlotParams or a PlotParams

    We could also use a type like: Callable[[Any], PlotParams]

    But a protocol will ensure the function will be able to use the argument as expected.

    """

    @property
    def level(self) -> int: ...

    @property
    def uid(self) -> str: ...

    @property
    def watermark(self) -> str: ...

    @property
    def dpi(self) -> int: ...


@dataclass
class PlotParams:
    """A placeholder for plotting parameters to be communicated from high to low-level APIs

    Notes
    -----
    **About the `level` attribute**

    The `level` attribute does not relate to where in the code the plot is created.
    It is an attribute that is intended to be used by a function to check whether a plot should be generated or not.

    This provides a mechanism to define the minimal level of figures to be generated in the configuration.
    It can be seen as a `logging level <https://docs.python.org/3/library/logging.html#logging-levels>`_, but for plots.

    Example: If a function defines its own plot as a level 2, the plot should be generated only if the PlotParams.level is higher or equal to 2.

    The default value is from the configuration parameter `plots.level`.

    Expected list of possible values for `level`:

    - 0 < 10: Plots with debug purposes, related to low level data manipulation at load time
    - 10 < 20: Plots related to input or intermediate data, eg: data used as input for a fit/computation (basically the final state of input data loading and pre-processing, to be used by a fit)
    - >= 20: Plots related to fit/computation results

    See Also
    --------
    :attr:`do.commodities.VALID_FIGURE_CATEGORIES`
    """

    level: int = None
    """Minimal level of figures to be generated based on this set of plotting parameters. Default: 'plots.level'"""

    watermark: str = ""
    """A string to be printed on top of any plot."""

    dpi: int = None
    """The resolution of figures, in dots-per-inch. Default: 'plots.dpi' """

    uid: str = ""
    """An unique identifier string related to this object. Eg: Calibration or CalibrationSet uid, possibly for a specific configuration."""

    def __post_init__(self):
        """Valid and assign default attributes from the runtime configuration"""
        if self.level is None:
            import pydox as do  # Avoid circularity

            object.__setattr__(self, "level", do.get_params("plots.level"))

        if self.dpi is None:
            import pydox as do  # Avoid circularity

            object.__setattr__(self, "dpi", do.get_params("plots.dpi"))

    @classmethod
    def get(
        cls, obj: Optional[Callable | TPlotParams] = None, **kwargs
    ) -> "PlotParams":
        """Return a :class:``PlotParams`` instance from an object

        Behavior:

        - If object is None, return a default :class:``PlotParams`` instance with **kwargs.
        - If object is a partial of :class:``PlotParams``, return the called partial.
        - If object is an instance of :class:``PlotParams``, return it unchanged.

        In any other case, a :class:`ValueError` is raised.

        This class method can thus be used as an object validator, that will return an instance of :class:`PlotParams` or fails.

        Parameters
        ----------
        obj: None | partial(:class:``PlotParams``) | :class:``PlotParams``

        **kwargs:
            Passed to :class:``PlotParams`` if obj is None. Ignored otherwise.

        Returns
        -------
        :class:`PlotParams`
            An instance of :class:`PlotParams`

        Raises
        ------
        :class:`ValueError`
        """
        if obj is None:
            ppar = cls(**kwargs)
        elif callable(obj):
            if isinstance(obj, partial) and obj.func == PlotParams:
                ppar = obj()
            else:
                raise ValueError(f"A callable must be a partial of 'PlotParams'")
        elif isinstance(obj, PlotParams):
            return obj
        else:
            raise ValueError(f"This object cannot return a 'PlotParams' instance")
        return ppar
