# Development set-up

**From the repo. root**:

1. Conda env:
```
conda env create -f ci/requirements/py3.11-all-pinned.yml
```
This command will create and install a complete `pydox-dev` environment.

2: _Editable_ installation of `pydox`:
```bash
conda activate pydox-dev
pip install -e .
```

3. Add dev. environment kernel to Jupyter:
```bash
python -m ipykernel install --name pydox-dev --user
```
