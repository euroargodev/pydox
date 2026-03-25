Some documentation in here, before moving it to 'docs' later.
***


# Pydox Configuration Manager

The Pydox configuration set of parameters is defined in two, complementary, ways:
- a **default** configuration, from files loaded automatically in a specific sequence,
- an **on-demand** configuration, set in user's scripts with methods from the configuration API.

## Format and content of configuration files

Pydox uses the YAML file format and syntax.

Here is a sample of the Pydox configuration file:
```yaml
# ============================================= Argo Float data
argo:
  src: https://data-argo.ifremer.fr
  use: 3  # 1: raw, 2: adjusted, 3: adjusted if available else raw
  qcflags: # Which QC to use data for
    pres: [1, 2, 8]
    temp: [1, 2, 8]
    psal: [1, 2, 8]
    doxy: [1, 2, 8, 3]
  auto: False
  wmo: null
```
where:
- ``argo`` is at the _root_ level and is a group,
- ``src`` is a parameter key, from which 'https://data-argo.ifremer.fr' is a value,
- ``qcflags`` is a subgroup with several parameters.

Values can be strings, floats, integers, boolean and null. Groups and possibly subgroups are created using 2 blank spaces.

Hence, in a Pydox configuration file:
- parameters are organized into groups and possibly subgroups.
- there is no limit to subgroups nesting depth.
- In the Pydox APIs, groups, subgroups and parameters:
  - are meant to be accessed (get/set methods) with a _string-dotted_ syntax, eg:
      - ``'argo'`` points to the _group_ of parameters and subgroups,
      - ``'argo.qcflags'`` points to a _subgroup_ of parameters,
      - ``'argo.qcflags.temp'`` is a _parameter_ key. 
  - can be **read/get**, using the _string-dotted_ syntax, with ``do.get_params()`` 
  - can be **set**, using the _string-dotted_ syntax, with ``do.set_params()``
  - can be **reset** to default values, using the _string-dotted_ syntax, with ``do.reset_params()``


## Default configuration, from files

A Runtime Configuration (``rc``) set of parameters are first loaded from the Pydox installation root file (typically located at ``<INSTALLPATH>/pydox/static/pydoxrc``). This file is mandatory and always loaded, it holds the default and complete configuration of the library (although some parameters have empty values, like paths toward some dataset). We refer to it as the _factory_ configuration, users can't change this file.

So users can customize the Pydox configuration using one or more files that will overwrite factory values wherever necessary. We refer to it as the _default_ configuration.

When a user import the Pydox library, from a python script or the CLI, a runtime configuration set of parameters is built sequentially by automatically loading configuration files, a.k.a. ``pydoxrc`` files, in the following locations and sequence:

1. In the user configuration directory:
   - ``${PYDOXCONFIGDIR}/pydoxrc``, if ``$PYDOXCONFIGDIR`` is defined
   - else if ``$PYDOXCONFIGDIR`` is NOT defined, it depends on the platform:
     - On Linux,
         - ``$XDG_CONFIG_HOME/pydox/pydoxrc``, if ``$XDG_CONFIG_HOME`` is defined
         - or ``$HOME/.config/pydox/pydoxrc``, if ``$XDG_CONFIG_HOME`` is not defined
     - On other platforms,
         - ``$HOME/.pydox/pydoxrc``, if ``$HOME`` is defined
2. In the current directory:
    - ``$PWD/pydoxrc``
3. In the user environment variable:
    - ``$PYDOXRC/pydoxrc``, if ``$PYDOXRC`` is defined and a directory,
    - directly ``$PYDOXRC`` if it is not a directory.

This hierarchy allows users to customize different group of configuration parameters at the level they choose. 
For instance:
- whatever the working DMQC session, the _User configuration directory_ level is a good location to set operator's name,
- for a given DMQC session, the _current folder_ and/or _os environment_ levels can be used to set reporting templates or paths toward dataset depending on the executing platform.

About the user configuration directory:
- it must be writable,
- is a temporary writable folder if none of the above directories is possible (so that Pydox will always have a writable configuration folder at runtime).

Note that the list of configuration files loaded at runtime can be seen with:
```python
import pydox as do
do.config_files()
```


## On-demand configuration, from the API

Once Pydox is imported, and the _default_ configuration is loaded from files (see above), users can read and further customize parameters using the following APIs:

### Parameter setter

Parameters are organized in group and subgroup, so that all parameters of a configuration can be uniquely referenced using a **string-dotted** syntax where groups and subgroups of parameters are joined with a dot to create a unique string. For instance:
- the Argo data source to be used by Pydox is in the ``argo`` group and is referenced as ``argo.src``.
- the list of QC flags to select pressure and temperature measurements are also in the ``argo`` group but in the ``qcflags`` subgroup, hence referenced as ``argo.qcflags.pres`` and ``argo.qcflags.temp``.

All parameters, groups and subgroups values can be set using the **string-dotted** syntax.

To set one parameter:
```python
do.set_params('argo.src', 'https://data-argo.ifremer.fr')
do.set_params('argo.qcflags.pres', [1,2,8])
do.set_params('argo.use', 2)
```
where the first argument of ``set_params`` is a string pointing to the parameter to set, and the second argument is the value to assign. 

In order to set more than one parameter from a given group or subgroup in one call to ``set_params``, we can use the **keyword arguments** syntax:
```python
do.set_params('argo', src='https://data-argo.ifremer.fr', use=2, qcflags={'pres': [1,2,8]})
```
This syntax can also be used to set subgroups:
```python
do.set_params('argo.qcflags', pres=[1,2,8], psal=[1,2,8])
```

Another approach is to provide only a **dictionary** to ``set_params``:
```python
do.set_params({'argo.src': 'https://data-argo.ifremer.fr'})
do.set_params({'argo.use': 2})
do.set_params({'argo.qcflags': {'pres': [1,2,8]}})
```
or by adding one more nesting level to set more than one parameter at a time:
```python
do.set_params({'argo': {'src': 'https://data-argo.ifremer.fr', 'use': 2, 'qcflags': {'pres': [1,2,8]}}})
```
where ``set_params`` now takes a dictionary as a single argument where keys based on the string-dotted syntax seen above.


### Parameter getter

All parameters, groups and subgroups values can be get with the **string-dotted** syntax:
```python
do.get_params('argo.src')  # One parameter
do.get_params('argo')  # A group of parameters
do.get_params('argo.qcflags')  # A subgroup of parameters
```

### Parameter reset

Last, all parameters, groups and subgroups values can be reset to their _default_ values with the **string-dotted** syntax:
 
```python
do.reset_params('argo.src')  # One parameter
do.reset_params('argo')  # A group of parameters
do.reset_params('argo.qcflags')  # A subgroup of parameter
do.reset_params() # All parameters !
```

### Print

In order to check at the full configuration, one can use the ``print`` function:

```python
import pydox as do
do.config_print()
```

This will return a pretty print of the full configuration, in HTML in jupyter notebook cells, otherwise as a pure string.


## Internals, for Pydox team

### About the full set of configuration parameters

- It is assumed to be an object of type: dict[str, Any]. But this could change in the future.
- The _default_ configuration is constructed when Pydox is imported with ``do.config.load_configs()`` by a sequential loading sequence of several files looked for in builtin locations (but possibly customized with environment variables, see below). This sequence of files can be returned by ``do.config_files()``.

- The ordered list of all possible _default_ configuration files is:
    - From the Pydox distribution (_factory_ configuration), ie where Pydox is installed, eg:
        - ``${HOME}/bin/conda/envs/pydox-dev/lib/python3.11/site-packages/pydox/static/pydoxrc``
    - From the user configuration folder, eg:
        - ``${PYDOXCONFIGDIR}/pydoxrc`` or
        - ``${XDG_CONFIG_HOME}/pydox/pydoxrc`` or
        - ``${HOME}/.config/pydox/pydoxrc`` or
        - ``${HOME}/.pydox/pydoxrc``
    - From current executing path, ie from the environment variable:
        - ``${PWD}/pydoxrc``
    - From the executing environment, ie from the environment variable:
        - ``${PYDOXRC}`` or
        - ``${PYDOXRC}/pydoxrc``

- The object with the full set of configuration parameters is accessible as: ``do.params``.

- The object ``do.params`` is **NOT** meant to be modified directly (huge risk of un-expected side effects): internals and users should use the ``do.set_params()`` method instead.

### Environment variables

Here is the list of relevant environment variables that can be used to customize where to look for default configuration files (see documentation):
- ``PYDOXCONFIGDIR``
- ``XDG_CONFIG_HOME``
- ``PYDOXRC``
