# Development set-up

```
conda env create -f requirements/py3.11-all-pinned.yml
```
This command will create and install a complete `pydox-dev` environment.

Don't forget to add this environment kernel to Jupyter:
```bash
python -m ipykernel install --name pydox-dev --user
```
