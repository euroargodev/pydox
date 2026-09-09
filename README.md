|    <img src="docs/_static/pydox_logo_long.png" alt="pydox logo" width="300"/><br>``pydox`` is a Python library dedicated to Argo Oxygen data Calibration and Adjustment    |
|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|
|                                            ‼️ **Pydox** is in active development phase and cannot be used as it is right now ‼️                                            |



**Pydox** is designed to compute oxygen calibration for Argo floats during Delayed-Mode Quality Control (DMQC). It helps users:
- Calculate gain, drift, and other calibration parameters with several methodology (in-air, climatology and reference CTD measurements), 
- Determine if adjustments are needed (via plots and metrics), 
- Apply calibrations to raw float data,
- Save adjusted data as DAC-ready Argo NetCDF files (BD files).

📚 The user API design proposal (i.e. how **pydox** shall be used by DMQC operators) is available here: https://archimer-intranet.ifremer.fr/doc/01015/112667


## Usage

This is the current state of the **pydox** API and expected use case:

### Load float and set-up a Calibration

```python
import pydox as do
import argopy as ar

# Print the configuration:
do.config_print()

# Connect to an Argo float to process:
a_float = ar.ArgoFloat(6902882, cache=True)
print(a_float)

# Setup a calibration:
c = do.Calibration('in_air', name='Demo')
# Set generic parameters:
c.set_params('calibration_parameters', cycles=[1, 100])
# c.set_params('calibration_parameters', fit_drift=[False, True])

# Set in-air method specific parameters:
c.set_params('calibration_methods.in_air', carryover=[False, True])

print(c)
```

### Fit calibration coefficients for all configurations
```python
# Compute calibrations coefficients for all possible configurations:
c.fit(a_float)

# Attributes as dict with configuration number as key: 
c.configs  # Configuration parameters
c.input_data # Data used as input for fit

c.coefs # Fit results coefficients
c.fit_data # Fit auxiliary data
```

### Check out figures

In order to display figures associated with this Calibration instance, you can use the `plot` method:

```python
c.plot() # Will show the highest level figures (most synthetic)
c.plot(0, categories='debug') # Show debugging figures for configuration #0
c.plot(1, categories='input_data') # Show figures from input data for configuration #1
c.plot(categories='fit_results') # Show figures from fit results with default layout ('hue')
c.plot(categories='fit_results', configs_layout='subplot') # Show figures from fit results with a specific layout
```

### Selecting best fit

Once you selected the configuration id giving the best fit, you can commit this information to the Calibration instance like this:

```python
c.set_best_fit(0) # 0 is the configuration id of the user-selected best fit
```

### HTML report

You can automatically generate a HTML report with:
```python
c.to_report(a_float, 'preliminary_report')
```

### BD files creation

And finally generate the BD files with the adjusted values with:
```python
c.create_corrBfile(a_float)
```

### Tips

Only trigger load without fit and access input data:
```python
# Trigger input data loading
c.load_input_data(a_float)  

# Access to input data: 
input_data_for_fit = c.input_data
```

Load and process Argo data, low-level with explicit list of parameters:
```python
from pydox.io.argo.facade import get_argo_data_for_in_air_method

argo_data = get_argo_data_for_in_air_method(
    cycles = a_float.CYCLE_NUMBERS,
    Sprof = a_float.dataset('Sprof'),
    Rtraj = a_float.dataset('Rtraj'),
    
    min_pres = do.get_params("argo.in_water_salinity.min_pressure"),
    max_pres = do.get_params("argo.in_water_salinity.max_pressure"),
    in_air_codes = do.get_params("argo.codes.in_air"),
    in_water_codes = do.get_params("argo.codes.in_water"),
    which_psal = do.get_params("argo.use"),
)

# Which is basically equivalent to:
# get_argo_data_for_in_air_method(
#     cycles = a_float.CYCLE_NUMBERS,
#     Sprof = a_float.dataset('Sprof'),
#     Rtraj = a_float.dataset('Rtraj'),
#     
#     min_pres = 0.,
#     max_pres = 10.,
#     in_air_codes = [699, 711, 799],
#     in_water_codes = [690, 710],
#     which_psal = 3,
# )
```

And then load NCEP data, which depends on the Argo data:
```python
from pydox.io.ncep.facade import get_ncep_data_for_in_air_method

d = get_ncep_data_for_in_air_method(argo_data)
```

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
- The class ``Calibration`` purpose is to explore the parameter space of a given method (eg: in-air). Some input data can be cached to be re-used rapidly throughout this sub-parameter space if needed, to improve performances.

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
│   ├── facade.py          # Wrapper for `Calibration` and `CalibrationSet` implementation
│   ├── spec.py            # The inner machinery: `Workflow`, one base class to rule them all
│   ├── method.py          # `Method` base class for method implementations
│   └── methods/           # Submodules for each method implementation
│       ├── in_air/        # In-air calibration
│       │   ├── plots.py   # Specific plot functions
│       │   ├── spec.py    # `MethodInAir` implementation
│       │   └── utils.py   # Specific high-level utilities, eg wrapper for Argo/NCEP data loading 
│       └── climatology.py # Climatology-based calibration
│
├── core/                 # Core Maths and Chemistry functions
│   ├── models.py         # Curve fitting models (functions passed to scipy.optimize.curve_fit)
│   └── in_air.py         # Functions for in-air methodology fit computations of G/D/C
│
├── io/                  # Low-level Data Input/Output handling
│   ├── argo/            # IO tools for Argo data
│   │   ├── facade.py    # Facade functions used by calibration method implementations
│   │   ├── types.py     # Document object exchanged by functions
│   │   └── utils.py     # All functions used to load/process Argo data in facade functions
│   └── ncep/            # IO tools for NCEP data
│       ├── facade.py    # Facade functions used by calibration method implementations
│       └── utils.py     # Utilities for NCEP data manipulation
│
├── reporting/            # Everything related to reporting emanating from Pydox (to users, to dev., on screen, to files) 
│   ├── colors.py         # Color scheme handling
│   ├── facade.py         # 
│   ├── html.py           # HTML report creation
│   ├── logs.py           # Logging system for users and dev.
│   └── pdf.py            # Export the figure registry to a single pdf document
│
├── utils/                # Non-specific utilities (low-level/limited-scope/autonomous functions)
│   ├── casting.py        # Enforce object types
│   ├── chemistry.py      # Chemistry variables computation/manipulation 
│   ├── compute.py        # Handle serial or parallel low-level fit functions execution 
│   └── xarray.py         # Utilities for xarray objects, specific to Pydox 
│
├── static/               # Static data files required internally
│   ├── templates/        # Jinja2 Template files
│   │   ├── default.html  # HTML template
│   │   └── img/          # Image files for templates
│   ├── mplstyle          # Matplotlib style sheet
│   ├── style.css         # A CSS stylesheet to be used in HTML rendering of pydox object in notebooks
│   └── pydoxrc           # Factory configuration file
│
├── tests/                # Unit and integration tests
│   ├── test_config.py    # Tests for pydox._config module
│   ├── test_io_ncep.py   # Tests for io.ncep module
│   ├── conftest.py       # Pytest configuration
│   └── pytest.ini        # Pytest parameters
│
└── errors.py             # Custom Pydox error messages
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
