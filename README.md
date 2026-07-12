# Admin Helper


## Development and tests

Install the project including its development dependencies:

```bash
uv sync --dev
```

Run the complete test suite:

```bash
uv run pytest
```

Run the suite with a coverage report:

```bash
uv run pytest --cov=admin_helper --cov-report=term-missing
```

More commands and examples are documented in [`docs/testing.md`](docs/testing.md).

## Examples

The object-framework demonstration was moved out of the package entry point:

```bash
uv run python examples/object_registry_demo.py
```

The temporary module entry point can be run with:

```bash
uv run python -m admin_helper
```
