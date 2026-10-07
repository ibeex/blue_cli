# blue_cli

A command-line interface for controlling BlueOS music players, supporting local USB music libraries, Tidal streaming, and AI-powered music recommendations.

## Features

- **Local Music Control**: Browse and play music from USB-connected libraries
- **Online Streaming**: Stream music directly from Tidal
- **AI Recommendations**: Get personalized music suggestions based on currently playing artist/album or custom text prompts, powered by OpenAI or OpenRouter
- **Interactive Selection**: Use fzf for intuitive music browsing
- **Command Aliases**: Supports partial command matching (e.g., `blue ran` for `blue random`)
- **Volume Control**: Gradual volume changes to prevent audio shock
- **Playlist Management**: Create and manage playlists
- **Extensive Caching**: 24-hour cache for improved performance

## Requirements

- Python 3.12+
- `fzf` command-line tool (required for interactive selection)
- BlueOS-compatible music player
- OpenAI or OpenRouter API key (for AI recommendations)

## Installation

### Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd blue_cli

# Install dependencies
just install
# or
uv sync --all-extras

# Run the CLI
uv run blue_cli --help
```

### Production Install

```bash
# Install from source
uv pip install .

# Or install in development mode
uv pip install -e .
```

## Configuration

The CLI uses these default settings:
- **BlueOS Host**: `192.168.88.15:11000`
- **Cache Directory**: `~/.cache/blue/`
- **Config Directory**: `~/.config/blue_cli/`

### BlueOS Server Configuration

You can configure the BlueOS host and port by creating a configuration file at `~/.config/blue_cli/keys.json`:

```json
{
  "host": "192.168.1.100",
  "port": 11000
}
```

**Configuration Options:**
- `host`: BlueOS server IP address (optional, defaults to `192.168.88.15`)
- `port`: BlueOS server port (optional, defaults to `11000`)

If no configuration file exists or these keys are missing, the CLI will use the default values.

### API Configuration

Configure your AI provider using either:

1. **Environment variable**:
   ```bash
   export OPENAI_API_KEY="your-api-key"
   ```

2. **Configuration file** at `~/.config/blue_cli/keys.json`:

   **For OpenAI:**
   ```json
   {
     "host": "192.168.1.100",
     "port": 11000,
     "api_key": "sk-your-openai-key",
     "model": "gpt-4o"
   }
   ```

   **For OpenRouter:**
   ```json
   {
     "host": "192.168.1.100",
     "port": 11000,
     "api_key": "sk-or-v1-your-openrouter-key",
     "base_url": "https://openrouter.ai/api/v1",
     "model": "anthropic/claude-3.5-sonnet"
   }
   ```

   **Configuration Options:**
   - `host`: BlueOS server IP address (optional, defaults to `192.168.88.15`)
   - `port`: BlueOS server port (optional, defaults to `11000`)
   - `api_key`: Your API key (required for AI features)
   - `model`: AI model to use (optional, defaults to `gpt-5`)
   - `base_url`: API endpoint URL (optional, defaults to OpenAI)

## Usage

### Basic Commands

```bash
# Browse and play local music
blue_cli usb

# Search Tidal online streaming
blue_cli online

# Get AI recommendations based on currently playing track
blue_cli ai

# Get AI recommendations based on custom text prompt
blue_cli ai "relaxing jazz for studying"
blue_cli ai "give me 8 ambient albums"

# Test mode: preview recommendations without adding to queue
blue_cli ai --test
blue_cli ai "upbeat rock music" --test

# Control playback
blue_cli play
blue_cli pause
blue_cli next
blue_cli previous

# Volume control
blue_cli volume 50
blue_cli volume +10
blue_cli volume -5
```

### Custom AI queries

Custom prompts honor the requested quantity and ordering, defaulting to five albums when no
quantity is specified. Classical queries request specific recordings with their credited
performers, orchestras, or conductors, plus a composer/work identifier for broader searches.
Direct matching tolerates punctuation, accents, and separate artist credits, but checks album
names and work numbers. When no direct match exists, searches also try shortened titles and
composer/work queries. Up to 20 deduplicated, ranked Tidal candidates are shown to the AI so it
can select an existing album ID rather than guessing release names. Unknown IDs are rejected.
If no candidate fits, the AI can correct its recommendation and try again, with at most two
clarification attempts per recommendation. Repeated answers are skipped, and duplicate albums
are not added twice within one request. Candidate selection is AI-assisted, not a guarantee of
catalogue accuracy or complete track contents.

Classical work requests validate the resolved albums' actual track lists before queue changes.
Composition identity uses composer, work type/instrument, and work or catalogue number—not the
recording artist or album ID. This covers numbered concertos, symphonies, sonatas, quartets,
trios, and suites. Number/catalogue aliases come from metadata, not composer-specific tables.
If track titles are ambiguous, an additional AI call identifies works from the actual track
list; unknown IDs, inconsistent identities, and uncertain answers are rejected.

Blue CLI is album-centric: AI recommendations always queue whole albums, never individual
tracks or movements. Track lists are used only to validate composition identity and coverage.
Coupled albums may supply multiple requested works, but albums repeating already-selected works
or introducing unrequested works are rejected. The AI can select another release, with rejected
album IDs excluded from subsequent searches. If the recommendation set's complete coverage
cannot be achieved with non-overlapping whole albums, nothing is added. Queue-update failures
may still leave a partial queue because the player offers no transaction. Explicit requests
for different recordings or interpretations retain repeated works. Coverage applies within one
command, not to the player's existing queue. Unrecognized work identities still use album-level
matching; AI identification and catalogue metadata do not guarantee musicological accuracy.

### Optional paid Beethoven smoke test

The automated tests use mocked AI and Tidal responses, including first-four-symphonies scenarios
with differing artist credits, subtitles, and candidate-ID clarification.
Run this live test separately; it requires API credentials and a player with Tidal configured.
Even `--test` makes paid AI calls, including clarification and explanation requests:

```bash
uv run blue_cli ai "give me first 4 symphonies by Beethoven" --test
```

Check that the matches cover symphonies 1–4 in order. To enqueue instead, run the command without
`--test`. This makes a new AI request, so recordings may differ from the preview. If complete
work coverage cannot be verified from the resolved track lists, the queue is left unchanged.

### Command Aliases

The CLI supports partial command matching:
```bash
blue ran    # same as: blue random
blue vol    # same as: blue volume
blue on     # same as: blue online
```

## Development

### Development Commands

```bash
# Install dependencies
just install

# Run all checks (install, lint, test)
just

# Run linting only
just lint

# Run tests
just test

# Build package
just build
```

### Architecture

- **Service Layer**: Modular services for USB, Tidal, AI, and playlist management
- **Base Client**: Common HTTP client for BlueOS XML API communication
- **Caching**: Aggressive caching using diskcache for performance
- **Interactive UI**: fzf integration for music selection

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

## License

MIT
