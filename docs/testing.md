# Testing

The project uses [pytest](https://pytest.org/) and stores test dependencies in the `dev` dependency group.

## Install or update the environment

```bash
uv sync --dev
```

## Run all tests

```bash
uv run pytest
```

For compact output:

```bash
uv run pytest -q
```

## Run tests with coverage

```bash
uv run pytest --cov=admin_helper --cov-report=term-missing
```

To additionally create an HTML coverage report:

```bash
uv run pytest --cov=admin_helper --cov-report=term-missing --cov-report=html
```

Open `htmlcov/index.html` afterwards.

## Run one file or one test

```bash
uv run pytest tests/test_fields.py
uv run pytest tests/test_fields.py::test_fields_discovers_stored_and_computed_fields
```

## Useful pytest flags

```bash
uv run pytest -x        # stop after the first failure
uv run pytest -vv       # show more detail
uv run pytest -s        # do not capture stdout/stderr
uv run pytest --lf      # rerun tests that failed last time
```

`src/admin_helper/__main__.py` is excluded from coverage because it contains example code rather than library functionality.
