# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

description: General Guidelines
globs:
alwaysApply: true

---

# Assistant Rules

Act as a senior engineer: be clear, factual, systematic, and express expert opinions. Suggest better approaches when applicable.

Core principles:

- Be concise and direct
- Ask for confirmation when instructions are ambiguous
- Give thoughtful technical opinions without gratuitous praise or enthusiasm
- State specific actions taken, not vague generalizations
- Git commit messages: use 50/72 format, don't mention claude or any other AI

## Comments

- Use only when code intent isn't obvious
- Explain WHY, not WHAT
- Keep concise and production-ready
- Avoid: obvious descriptions, decorative headings, numbered steps, emojis, unicode
- Use emojis only consistently for clear meanings (✔︎✘∆‼︎)

---

description: Python Coding Guidelines
globs: \*.py,pyproject.toml
alwaysApply: false

---

# Python Guidelines

Target Python 3.12-3.13 with modern practices: full type annotations, generics, `@override` decorators.

## Development Commands

- Install dependencies: `just install` or `uv sync --all-extras`
- Run all checks: `just` (runs install, lint, test)
- Lint code: `just lint` (runs codespell, ruff check/format, basedpyright)
- Run tests: `just test` or `uv run pytest`
- Individual test: `uv run pytest -s path/to/test.py`
- Run CLI: `uv run blue_cli` or `blue_cli` (if installed)

## Development Workflow

- Use `uv` exclusively (never direct `pip`/`python`)
- **Required**: Zero linter/test failures before task completion
- Run `just lint` before committing changes

## Development Standards

- Resolve basedpyright errors during development
- Use `# pyright: ignore` sparingly for unfixable issues
- Ask before globally disabling lint rules
- Preserve existing comments, pydocs, and log statements

## Imports & Conventions

- Use absolute imports: `from pkg.module import ...` (not relative)
- Import from correct modules: `collections.abc`, `typing_extensions`
- Use `pathlib.Path`, `Path.read_text()` over file operations

## Testing

- Complex tests: `tests/test_name.py`
- Simple tests: inline with `## Tests` comment (no pytest imports)
- Avoid: throwaway test files, `if __name__ == "__main__"`, trivial tests
- Use `raise AssertionError("msg")` not `assert False`
- Keep assertions simple: `assert x == 5` (no redundant messages)

## Types & Style

- Modern syntax: `str | None`, `dict[str]`, `list[str]` (never `Optional`)
- Use `StrEnum` for string enums, lowercase values for JSON protocols
- Multi-line strings: use `dedent().strip()`

## Docstrings

- Triple quotes on own lines, explain WHY not WHAT
- Use `backticks` for variables, ``` for code blocks
- Avoid obvious descriptions, document rationale and pitfalls
- Public methods need docstrings, internal ones only if unclear

## Best Practices

- Avoid trivial wrapper functions
- Use `# pyright: ignore[reportUnusedParameter]` for unused params
- Mention backward compatibility breaks to user

---

description: BlueOS Music Control CLI Architecture
globs: src/blue_cli/**/*.py
alwaysApply: false

---

# Architecture Overview

This is a CLI application for controlling BlueOS music players, supporting local USB music, Tidal streaming, and AI-powered music recommendations.

## Core Architecture

- **Entry Point**: `blue_cli.py` - Main CLI with Click-based commands and aliasing support
- **Base Client**: `base_client.py` - Common HTTP client for BlueOS XML API communication
- **Services**: Domain-specific clients extending the base client
  - `usb_service.py` - Local USB music library control (aliased as BlueSound)
  - `tidal_service.py` - Tidal streaming service integration
  - `playlist_service.py` - Playlist management functionality
  - `ai_service.py` - OpenAI-powered music recommendations
- **Configuration**: `config.py` - Default host/port, API keys, caching paths
- **Console**: `console.py` - Rich console formatting utilities

## Service Layer Pattern

All services inherit from `BluesoundBaseClient` which provides:
- HTTP GET/POST methods for BlueOS API
- XML response parsing via xmltodict
- Common error handling patterns
- JMESPath query utilities for XML data extraction

## Key Implementation Details

- **Command Aliasing**: Uses custom `AliasedGroup` for partial command matching
- **Dependency Injection**: `@with_blue_service` decorator injects service instances
- **Caching Strategy**: 24-hour cache for search results using diskcache
- **FZF Integration**: Required dependency for interactive music selection
- **Volume Control**: Gradual stepping for changes >5 to prevent audio shock
- **AI Filtering**: Excludes rap/hip-hop genres from AI recommendations

## API Integration

- BlueOS XML API endpoint: `http://192.168.88.15:11000/Services`
- Uses HTTP GET for queries, POST for control commands
- All responses parsed from XML to Python dictionaries
- JMESPath used for extracting nested data from API responses

## Configuration Management

- Default BlueOS host: `192.168.88.15:11000`
- Cache directory: `~/.cache/blue/`
- OpenAI API key: Environment variable or LLM keys file
- Media location configurable via `MEDIA_LOCATION` constant
