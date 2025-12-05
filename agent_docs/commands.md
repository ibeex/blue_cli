# Development Commands

Complete reference for all development commands.

## Just Commands

Run via `just <command>` from project root.

### Default Workflow

```bash
just
```

Runs full workflow: install, lint, test

### Install Dependencies

```bash
just install
```

Installs all dependencies via `uv sync --all-extras`. Equivalent to running `uv sync --all-extras` directly.

### Linting

```bash
just lint
```

Runs all linters via `uv run python devtools/lint.py`:

- `codespell` - Spell checking
- `ruff check` - Python linting
- `ruff format` - Code formatting
- `basedpyright` - Type checking

### Testing

```bash
just test
```

Runs pytest via `uv run pytest`.

### Upgrade Dependencies

```bash
just upgrade
```

Upgrades all dependencies via `uv sync --upgrade --all-extras --dev`.

### Build Package

```bash
just build
```

Builds package via `uv build`. Creates dist/ with wheel and sdist.

### Clean Artifacts

```bash
just clean
```

Removes build artifacts:

- `dist/`
- `*.egg-info/`
- `.pytest_cache/`
- `.mypy_cache/`
- `.venv/`
- `__pycache__/`

### Release

```bash
just release [bump]
```

Automated release with version bump. Bump options: `major`, `minor` (default), `patch`.

Workflow:

1. Check working tree is clean
2. Bump version via `uv version --bump`
3. Commit changes
4. Create git tag
5. Print push instructions

## UV Commands

Direct `uv` usage (preferred over pip/python).

### Run Scripts

```bash
uv run blue_cli          # Run CLI
uv run pytest            # Run tests
uv run pytest -s path/to/test.py  # Run specific test
```

### Sync Dependencies

```bash
uv sync                  # Sync dependencies
uv sync --all-extras     # Include optional dependencies
```

## Pytest Options

### Run All Tests

```bash
uv run pytest
```

### Run Specific Test

```bash
uv run pytest -s path/to/test.py
```

The `-s` flag shows print statements and logs during test execution.

### Test Discovery

pytest discovers tests in:

- `src/` - Inline tests marked with `## Tests` comment
- `tests/` - Dedicated test files

Pattern: `test_*` functions in `Test*` classes or standalone.

## CLI Invocation

### Via UV

```bash
uv run blue_cli [command]
```

### Installed

If installed via `uv pip install -e .`:

```bash
blue_cli [command]
```

## Linter Configuration

Configured in `pyproject.toml`:

- **Ruff**: Line length 100, rules: E, F, UP, B, I
- **BasedPyright**: Basic type checking, includes src/tests/devtools
- **Codespell**: Spell checking
