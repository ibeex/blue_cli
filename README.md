# blue_cli

A command-line interface for controlling BlueOS music players, supporting local USB music libraries, Tidal streaming, and AI-powered music recommendations.

## Features

- **Local Music Control**: Browse and play music from USB-connected libraries
- **Tidal Integration**: Stream music directly from Tidal
- **AI Recommendations**: Get personalized music suggestions powered by OpenAI or OpenRouter
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
     "api_key": "sk-your-openai-key",
     "model": "gpt-4o"
   }
   ```

   **For OpenRouter:**
   ```json
   {
     "api_key": "sk-or-v1-your-openrouter-key",
     "base_url": "https://openrouter.ai/api/v1",
     "model": "anthropic/claude-3.5-sonnet"
   }
   ```

   **Configuration Options:**
   - `api_key`: Your API key (required)
   - `model`: AI model to use (optional, defaults to `gpt-5`)
   - `base_url`: API endpoint URL (optional, defaults to OpenAI)

## Usage

### Basic Commands

```bash
# Browse and play local music
blue_cli usb

# Search Tidal
blue_cli tidal

# Get AI music recommendations
blue_cli ai "relaxing jazz for studying"

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

### Command Aliases

The CLI supports partial command matching:
```bash
blue ran    # same as: blue random
blue vol    # same as: blue volume
blue ti     # same as: blue tidal
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
