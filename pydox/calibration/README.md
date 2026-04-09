
# Usage

Misc. requirements and/or comments:
- [x] The configuration manager (#2 ) is a high level API for users
- [x] So users can provide one or more possible values for relevant settings with the configuration manager, (define the config space to explore)
- [x] Internally, pydox is able to flatten this config space (settings arrays) to create a collection of unique settings for computations to be executed by calculation subroutines.
- [x] the collection of computations can be executed in parallel or sequentially:  take care of serialization
- [x] Need to identify how settings and eventually data are passed down to calculation subroutines: work with dataclass, not configuration object

Todo:
- calculation subroutines,
- data download
- argo object
- ...

## Examples

### For a `Calibration`

Using the default configuration:

```python
from pydox import Calibration

c = Calibration('in_air')
c
```
```
<pydox.Workflow.Calibration.in_air> 'This Would Be A Long Name For The 'In Air' Methodology'
fitted: False

parameters (shared by all methods):
  piecewise: {"auto_segment": false, "nb_segments": 1, "auto_break": true, "breakpoints": null}
  initial_guess: {"gain": 1.0, "drift": 0.0}
  cycles: ["first", "last"]
  fit_drift: false

parameters (specific to 'in_air'):
  carryover: False
  dataset: 'ncep'
    name: "NCEP 2, real-time ?"
    src: "/Users/gmaze/ARGO_NEW/NEW_LOCODOX/NCEP_DATA/"

configurations [1]:
  0: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1000, 'carryover': False, 'dataset': 'ncep', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
```

Or using a range of parameters:

```python
c = Calibration('in_air')
c.set_params('calibration_methods.in_air', carryover=[False, True])
c
```
```
<pydox.Workflow.Calibration.in_air> 'This Would Be A Long Name For The 'In Air' Methodology'
fitted: False

parameters (shared by all methods):
  piecewise: {"auto_segment": false, "nb_segments": 1, "auto_break": true, "breakpoints": null}
  initial_guess: {"gain": 1.0, "drift": 0.0}
  cycles: ["first", "last"]
  fit_drift: false

parameters (specific to 'in_air'):
  carryover: [false, true]
  dataset: 'ncep'
    name: "NCEP 2, real-time ?"
    src: "/Users/gmaze/ARGO_NEW/NEW_LOCODOX/NCEP_DATA/"

configurations [2]:
  0: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1000, 'carryover': False, 'dataset': 'ncep', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
  1: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1001, 'carryover': True, 'dataset': 'ncep', 'initial_carryover': {'value': 0.0, 'error': 0.0}
```

### For a `CalibrationSet`

```python
from pydox import Calibration, CalibrationSet

s = CalibrationSet()
s.commit(Calibration('in_air').set_params('calibration_methods.in_air', carryover=[False, True], dataset=['ncep', 'era5']))
s.commit(Calibration('climatology').set_params('calibration_methods.climatology.max_pressure', [25., 50.]))
s
```
```
<pydox.Workflow.CalibrationSet>
fitted: False

parameters (shared by all methods):
  piecewise: {"auto_segment": false, "nb_segments": 1, "auto_break": true, "breakpoints": null}
  initial_guess: {"gain": 1.0, "drift": 0.0}
  cycles: ["first", "last"]
  fit_drift: false

configurations [6]:
  0: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1000, 'carryover': False, 'dataset': 'ncep', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
  1: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1001, 'carryover': False, 'dataset': 'era5', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
  2: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1002, 'carryover': True, 'dataset': 'ncep', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
  3: method='in_air' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1003, 'carryover': True, 'dataset': 'era5', 'initial_carryover': {'value': 0.0, 'error': 0.0}}
  4: method='climatology' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1000, 'min_pressure': 0.0, 'max_pressure': 25.0, 'dataset': 'woa'}
  5: method='climatology' {'fit_drift': False, 'initial_gain': {'value': 1.0, 'error': 0.0}, 'initial_drift': {'value': 0.0, 'error': 0.0}, 'cycles': ['first', 'last'], 'dummy': 1001, 'min_pressure': 0.0, 'max_pressure': 50.0, 'dataset': 'woa'}
```
## Known limitations

The `CalibrationSet.commit()` method implementation does not allow for an instance to propagation parameter values to committed objects as expected:

```python
from pydox import Calibration, CalibrationSet

# not correct: the config list only depends on commited object, which ignore the calibrationset change of value for fit_drift
s = CalibrationSet()
s.set_params('calibration_parameters.fit_drift', [False, True])
s.commit(Calibration('in_air').set_params('calibration_methods.in_air', carryover=[False, True]))
s
```
This returns 2 configurations for `carryover=[False, True]`, but the `fit_drift=[False, True]` is ignored and the global value `False` is used when the `Calibration('in_air')` is called within the `.commit()`.

To fix this, we need to modify global settings so that committed object is aware of a change of value for `fit_drift`:

```python
import pydox as do:

do.set_params('calibration_parameters.fit_drift', [False, True])

s = CalibrationSet()
s.commit(Calibration('in_air').set_params('calibration_methods.in_air', carryover=[False, True]))
s
```
And now this return 4 configurations for `carryover=[False, True]`, and `fit_drift=[False, True]`.

This is an unexpected behaviour that should be fixed in another PR.

## Diagram showing this PR implementation:

![pydox-implementation 001](https://github.com/user-attachments/assets/7e3bc3d1-27c9-4296-acc3-c9073658452b)




# Implementations

## Workflow

```python
class Workflow(ABC): # Base class for one or more calibrations

    def __init__(self, *args, **kwargs): ...

    @classmethod
    def from_config(cls, config, *args, **kwargs) -> "Workflow": ...

    def _repr_params_shared(self) -> list[str]: ...

    def _repr_configs(self) -> list[str]: ...

    def _repr_fitted(self)->list[str]: ...

    def __repr__(self): ...

    @property
    def fitted(self) -> bool: ...

    def get_params(self, *args, **kwargs): ...

    def set_params(self, *args, **kwargs) -> Self: ...

    def reset_params(self, *args, **kwargs) -> Self: ...

    def _sparam(self, param: Optional[str] = None, fallback: Optional[Any] = None) -> Any: ...

    @property
    def configs(self) -> ConfigsDict: ...

    @property
    def n_configs(self) -> int: ...

    @property
    def coefs(self) -> CoefsDict: ...

    @abstractmethod
    def _flatten_configs(self) -> ConfigsDict: ...

    @abstractmethod
    def fit(self, data: Any) -> Self: ...

```

### Method

```python

class Method(Workflow, ABC): # Base class for one methodology implementation
    
    rcgroup: str

    def __init__(self, *args, **kwargs): ...

    def _mparam(self, param: str, fallback: Optional[Any] = None) -> Any: ...

    @property
    def method(self) -> str: ...

    def _repr_dataset(self) -> list[str]: ...

    @abstractmethod
    def _repr_params(self) -> list[str]: ...

    @abstractmethod
    def _repr_coefs(self) -> list[str]: ...

    def __repr__(self): ...
```

#### MethodInAir

```python

class MethodInAir(Method):
    rcgroup = "in_air"

    def __init__(self, *args, **kwargs): ...

    def _repr_params(self) -> list[str]: ...

    def _flatten_configs(self) -> ConfigsDict: ...

    def fit(self, argofloat_obj: Optional[Any] = None, method: str = "sequential") -> Self: ...

    def _repr_coefs(self) -> list[str]: ...
```

#### MethodClimatology

```python

class MethodClimatology(Method):
    rcgroup = "climatology"

    def __init__(self, *args, **kwargs): ...

    def _repr_params(self) -> list[str]: ...

    def _flatten_configs(self) -> ConfigsDict: ...

    def fit(self, data: Any) -> Self: ... # NotImplementedError
```
### CalibrationSet

```python

class CalibrationSet(Workflow): # Facade to handle a collection of methodology implementations

    def __init__(self, *args, **kwargs): ...
    
    def __repr__(self): ...

    def commit(self, m: MethodInAir | MethodClimatology) -> Self: ...

    def _flatten_configs(self) -> ConfigsDict: ...

    def fit(self, data: Any) -> Self: ... # NotImplementedError
```