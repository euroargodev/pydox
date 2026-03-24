| <img src="docs/_static/pydox_logo_long.png" alt="pydox logo" width="300"/><br>``pydox`` is a python Python library dedicated to Argo Oxygen data Calibration and Adjustment |
|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|
|                                            ‼️ **Pydox** is in active development phase and cannot be used as it is right now ‼️                                             |



**Pydox** is designed to compute oxygen calibration for Argo floats during Delayed-Mode Quality Control (DMQC). It helps users:
- Calculate gain, drift, and other calibration parameters with several methodology (in-air, climatology and reference CTD measurements), 
- Determine if adjustments are needed (via plots and metrics), 
- Apply calibrations to raw float data,
- Save adjusted data as DAC-ready Argo NetCDF files (BD files).

📚 The user API design proposal (i.e. how **pydox** shall be used by DMQC operators) is available here: https://archimer-intranet.ifremer.fr/doc/01015/112667

### Library structure

All submodules are tentatively listed below according to user-level exposition: ``calibration`` is the primary object to work with, while ``tests`` is surely for devs. only.

In short:
- The class ``Calibration`` purpose is to explore the parameter space of a given method (eg: in-air). Input data can be shared throughout this sub-parameter space if needed, to improve performances.

- The class ``CalibrationSet`` main purpose is to explore the full configuration space, i.e. all parameters for all methods. An _un-ordered set_ can be computed in parallel to improve performances, while _ordered set_ define a calibration sequence of misc. methods, to allow operator to fully customize a calibration workflow. 

- The class ``Adjustment`` compute adjusted values and is intended to be used:
  - internally by ``Calibration`` and ``CalibrationSet`` (eg: ``.predict()`` method)
  - by users to create BD files (eg: ```.compute()``` and ```.to_netcdf()``` methods)

The complete user API will be documented progressively, first in docstrings, second in the online documentation.

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
├── config/               # Configuration manager
│   ├── yaml.py           # Functions specific to handling YAML configuration files
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
└── tests/               # Unit and integration tests
```

**Pydox** includes portions of Matplotlib, [...]. Their licenses are  included in the LICENSES directory.

***
This software is developed by:
<div>
<img src="https://www.umr-lops.fr/var/storage/images/_aliases/logo_main/medias-ifremer/medias-lops/logos/logo-lops-2/1459683-4-fre-FR/Logo-LOPS-2.png" height="75">
<a href="https://wwz.ifremer.fr"><img src="https://user-images.githubusercontent.com/59824937/146353099-bcd2bd4e-d310-4807-aee2-9cf24075f0c3.jpg" height="75"></a>
<img src="https://github.com/euroargodev/euroargodev.github.io/raw/master/img/logo/ArgoFrance-logo_banner-color.png" height="75">
</div>
