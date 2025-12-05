# Blue CLI

CLI for controlling BlueOS music players with USB, Tidal, and AI recommendations.

## Tech Stack

Python 3.12+ · Click · Rich · xmltodict · JMESPath · OpenAI

## Project Structure

- `src/blue_cli/blue_cli.py` - Entry point, Click commands
- `src/blue_cli/base_client.py` - HTTP client for BlueOS XML API
- `src/blue_cli/usb_service.py` - USB music library
- `src/blue_cli/tidal_service.py` - Tidal streaming
- `src/blue_cli/ai_service.py` - AI recommendations
- `src/blue_cli/playlist_service.py` - Playlist management
- `src/blue_cli/config.py` - Configuration defaults

## Development

```bash
just          # Install, lint, test
just lint     # codespell, ruff, basedpyright
just test     # pytest
```

## Standards

- Act as senior engineer: clear, factual, systematic
- Use `uv` exclusively (never pip/python directly)
- Zero linter/test failures before task completion
- Run `just lint` before committing

## Comments

- Use only when code intent isn't obvious
- Explain WHY, not WHAT
- Avoid obvious descriptions, decorative headings, numbered steps

## Architecture

- Services inherit from `BluesoundBaseClient`
- HTTP GET for queries, POST for control
- XML responses parsed via xmltodict
- `/Services` endpoint documents all BlueOS API endpoints

## Configuration

- Default host: `192.168.88.15:11000`
- Cache: `~/.cache/blue/`
- OpenAI key: Environment variable or LLM keys file

## Detailed Docs

See `agent_docs/`:

- `architecture.md` - Service patterns, caching, API details
- `commands.md` - All development commands
