.PHONY: all check test coverage lint format_check format typecheck demo run clean

all: check

check: coverage lint format_check typecheck

test:
	uv run pytest

coverage:
	uv run pytest --cov=admin_helper --cov-report=term-missing

lint:
	uv run ruff check .

format_check:
	uv run ruff format --check --diff .

format:
	uv run ruff format .

typecheck:
	uv run pyright

demo:
	uv run python examples/object_registry_demo.py

run:
	uv run python -m admin_helper

clean:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov