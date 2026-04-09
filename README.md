| <img src="docs/_static/pydox_logo_long.png" alt="pydox logo" width="300"/><br>``pydox`` is a python Python library dedicated to Argo Oxygen data Calibration and Adjustment |
|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|
|                                            ‼️ **Pydox** is in active development phase and cannot be used as it is right now ‼️                                             |



**Pydox** is designed to compute oxygen calibration for Argo floats during Delayed-Mode Quality Control (DMQC). It helps users:
- Calculate gain, drift, and other calibration parameters with several methodology (in-air, climatology and reference CTD measurements), 
- Determine if adjustments are needed (via plots and metrics), 
- Apply calibrations to raw float data,
- Save adjusted data as DAC-ready Argo NetCDF files (BD files).

📚 The user API design proposal (i.e. how **pydox** shall be used by DMQC operators) is available here: https://archimer-intranet.ifremer.fr/doc/01015/112667


## Development of the library

### Unit tests

We use [pytest](https://docs.pytest.org/en/stable/index.html) to implement unit testings.

All test files must be placed under ``pydox/tests`` and named after the module covered ``test_<mod>.py``.

The tests suite can be executed from the repo root with:
```bash
pytest -ra -v -s -c pydox/tests/pytest.ini --durations=10 --cov=./ --cov-config=.coveragerc --cov-report xml:pydox/tests/cov.xml --cov-report term-missing --log-file=pydox/tests/pydox-tests.log
```
Logs and coverage result files will be placed under ``pydox/tests``.

The [coverage](https://coverage.readthedocs.io/) report can be checked with:
```bash
coverage report --sort=cover --show-missing
```

### Local installation

Once the repo has been cloned locally, instead of using ``sys.path.append()`` to import Pydox, it is recommended to install the local distribution with pip.

From the repo root:
```bash
pip install -e .
```

This will install Pydox in the active Conda environment and make it _importable_ from any script.

### The library structure

All submodules are tentatively listed below in the "Structure by design" section, according to user-level exposition: ``calibration`` is the primary object to work with, while ``tests`` is surely for devs. only.

In short:
- The class ``Calibration`` purpose is to explore the parameter space of a given method (eg: in-air). Input data can be shared throughout this sub-parameter space if needed, to improve performances.

- The class ``CalibrationSet`` main purpose is to explore the full configuration space, i.e. all parameters for all methods. An _un-ordered set_ can be computed in parallel to improve performances, while _ordered set_ define a calibration sequence of misc. methods, to allow operator to fully customize a calibration workflow. 

- The class ``Adjustment`` compute adjusted values and is intended to be used:
  - internally by ``Calibration`` and ``CalibrationSet`` (eg: ``.predict()`` method)
  - by users to create BD files (eg: ```.compute()``` and ```.to_netcdf()``` methods)

The complete user API will be documented progressively, first in docstrings, second in the online documentation.

#### Current structure

Let's try to keep up to date the current pydox structure:

```bash
pydox/
│
├── commodities.py       # Objects to communicate stateful data between low and high level APIs 
│
├── _config/             # Configuration manager (private, user APIs defined at pydox module level)
│   ├── yaml.py          # Functions specific to handling YAML configuration files
│   ├── utils.py         # Specific utilities, possibly relying on high-level objects
│   └── config.py        # Primary functions to manage pydox settings
│
├── calibration/           # High-level user interface to running calibrations
│   ├── facade.py          # Provides `Calibration` and `CalibrationSet`
│   ├── spec.py            # The inner machinery: `Workflow`, one base class to rule them all
│   ├── method.py          # `Method` base class for method implementations, could be merge with spec.py
│   ├── utils.py           # Specific utilities, possibly relying on high-level objects
│   └── methods/           # Submodules for each method implementation
│       ├── in_air.py      # In-air calibration
│       └── climatology.py # Climatology-based calibration
│
├── core/                 # Core Maths and Chemistry functions
│   ├── models.py         # Curve fitting models (functions passed to scipy.optimize.curve_fit)
│   └── in_air.py         # Functions for in-air methodology fit computations of G/D/C
│
├── utils/                # Non-specific utilities (low-level/limited-scope/autonomous functions)
│   ├── casting.py        # Enforce object types
│   └── compute.py        # Handle serial or parallel low-level fit functions execution 
│
├── static/               # Static data files required internally
│   ├── style.css         # A CSS stylesheet to be used in HTML rendering of pydox object
│   └── pydoxrc           # Factory configuration file
│
└── tests/                # Unit and integration tests
    ├── test_config.py    # Tests for pydox._config
    ├── conftest.py       # Pytest configuration
    └── pytest.ini        # Pytest parameters
```

#### Structure by design
```bash
pydox/
│
├── calibration/           # Allows to work with one calibration method
│   ├── facade.py          # Class "Calibration" facade
│   ├── spec.py            # Specifications ("Calibration" prototype)
│   ├── methods/           # Submodules for each method implementation
│   │   ├── in_air.py      # In-air calibration
│   │   ├── climatology.py # Climatology-based calibration
│   │   └── reference.py   # Reference profile (rosette/ctd) calibration 
│   ├── utils.py           # Specific utility functions
│   └── plot.py            # Specific plot functions (backed by visualisation.plots)
│
├── calibrationset/      # DMQC step 1: decision making
│   ├── facade.py        # Class "CalibrationSet" facade
│   ├── spec.py          # Specifications ("CalibrationSet" logic)
│   ├── utils.py         # Specific utility functions
│   └── plot.py          # Specific plot functions (backed by visualisation.plots)
│
├── adjusment/           # DMQC step 2: compute/save adjusted values
│   ├── facade.py        # This is where we can apply calibration coefficients
│   ├── spec.py          # and Argo convention to produce BD files.
│   ├── utils.py         # Specific utility functions
│   └── plot.py          # Specific plot functions (backed by visualisation.plots)
│
├── reporting/            # Reporting tools (figures and documents)
│   ├── facade.py         # Class "Report" facade
│   └── spec.py           # Specifications ("Report" logic)
│
├── _config/              # Configuration manager
│   ├── yaml.py           # Functions specific to handling YAML configuration files
│   ├── utils.py          # Some specific utilities
│   └── config.py         # Facade to manage all pydox settings
│
├── visualisation/        # Low-level Data viz tools
│   ├── plots.py          # Plotting functions
│   └── gui.py            # Simple GUI for interactive comparison
│
├── core/                 # Core Maths and Chemistry functions (designed to be externalised)
│   ├── misc.py           # Any core functions to be sorted later
│   └── units.py          # Unit conversions functions
│
├── io/                  # Low-level Data Input/Output handling
│   ├── in_air/          # eg for in-air dataset
│   │   ├── dataset/     #
│   │   │   ├── ncep.py  # 
│   │   │   └── era5.py  #
│   │   ├── facade.py    # Facade used by the 'in-air' method
│   │   └── spec.py      # Data access specifications
│   ├── argofloatx.py    # Extension for argopy.ArgoFloat
│   └── bd.py            # Logic to save results in BD NetCDF files
│
├── static/               # Static data file required internally
│   ├── pydox.mplstyle    # Pydox matplotlib style sheet
│   ├── assets/           # 
│   │   └── templates/    # Remplates for reporting
│   │       └── lops.html #
│   └── pydoxrc           # Factory configuration file
│
└── tests/                # Unit and integration tests
    ├── test_config.py    # Tests for pydox._config
    ├── conftest.py       # Pytest configuration
    └── pytest.ini        # Pytest parameters
```

**Pydox** includes portions of Matplotlib, [...]. Their licenses are  included in the LICENSES directory.

***
This software is developed by:
<div>
<img src="https://www.umr-lops.fr/var/storage/images/_aliases/logo_main/medias-ifremer/medias-lops/logos/logo-lops-2/1459683-4-fre-FR/Logo-LOPS-2.png" height="75">
<a href="https://wwz.ifremer.fr"><img src="https://user-images.githubusercontent.com/59824937/146353099-bcd2bd4e-d310-4807-aee2-9cf24075f0c3.jpg" height="75"></a>
<img src="https://github.com/euroargodev/euroargodev.github.io/raw/master/img/logo/ArgoFrance-logo_banner-color.png" height="75">
</div>
