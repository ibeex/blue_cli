# justfile for easy development workflows.
# See development.md for docs.
# Note GitHub Actions call uv directly, not this justfile.

# Run uv sync, lint, and test by default
default: install lint test

# Install dependencies
install:
	uv sync --all-extras

# Run linting
lint:
	uv run python devtools/lint.py

# Run tests
test:
	uv run pytest

# Upgrade dependencies
upgrade:
	uv sync --upgrade --all-extras --dev

# Build package
build:
	uv build

# Clean build artifacts
clean:
	-rm -rf dist/
	-rm -rf *.egg-info/
	-rm -rf .pytest_cache/
	-rm -rf .mypy_cache/
	-rm -rf .venv/
	-find . -type d -name "__pycache__" -exec rm -rf {} +