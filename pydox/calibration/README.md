
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

    def flatten_configs(self) -> ConfigsDict: ...

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