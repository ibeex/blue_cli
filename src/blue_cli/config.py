import json
import os
from pathlib import Path

# Default Server info, change these values to match yours.
HOST = "192.168.88.15"
PORT = 11000

__version__ = "1.0.0"
__author__ = "IbeeX"

MEDIA_LOCATION = "Library"
AI_MODEL = "openai/gpt-5.1-chat"
# Reasoning models count internal reasoning against this cap, so leave generous headroom.
AI_MAX_COMPLETION_TOKENS = 16000
# "low" is the cheapest level providers honour; recommendations do not need deep thinking.
AI_REASONING_EFFORT = "low"
REASONING_EFFORTS = ("minimal", "low", "medium", "high")
REASONING_OFF_VALUES = frozenset({"", "none", "off", "false", "0"})

home = Path.home()
cache_path = home / ".cache" / "blue"
config_path = home / ".config" / "blue_cli"
classical_artists_path = config_path / "classical_artists.txt"

DEFAULT_CLASSICAL_ARTISTS = frozenset(
    {
        "Antonio Vivaldi",
        "Daniil Trifonov",
        "Kate Liu",
        "Ludwig van Beethoven",
        "Pyotr Ilyich Tchaikovsky",
        "Sergei Rachmaninoff",
        "Sergei Rachmaninov",
        "Wolfgang Amadeus Mozart",
    }
)

if not cache_path.exists():
    cache_path.mkdir(parents=True)

if not config_path.exists():
    config_path.mkdir(parents=True)


def _load_keys_config() -> dict:
    """Load configuration from keys.json file, returning empty dict if not found or invalid."""
    keys_file = config_path / "keys.json"
    if keys_file.exists():
        try:
            with open(keys_file) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def get_openai_key() -> str | None:
    """Get OpenAI API key from environment or blue_cli keys file."""
    # Try environment variable first
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key

    # Try blue_cli keys file
    keys_data = _load_keys_config()
    return keys_data.get("api_key")


def get_ai_model() -> str:
    """Get AI model name from config file or default to AI_MODEL constant."""
    keys_data = _load_keys_config()
    return keys_data.get("model", AI_MODEL)


def get_max_completion_tokens() -> int:
    """Get max completion tokens from config file or a reasoning-friendly default."""
    value = _load_keys_config().get("max_completion_tokens")
    if isinstance(value, bool):
        return AI_MAX_COMPLETION_TOKENS
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return AI_MAX_COMPLETION_TOKENS


def get_reasoning_effort() -> str | None:
    """Get reasoning effort from config file, or None to leave the provider default."""
    value = _load_keys_config().get("reasoning_effort", AI_REASONING_EFFORT)
    if not isinstance(value, str):
        return AI_REASONING_EFFORT
    normalized = value.strip().lower()
    if normalized in REASONING_OFF_VALUES:
        return None
    return normalized if normalized in REASONING_EFFORTS else AI_REASONING_EFFORT


def get_base_url() -> str | None:
    """Get OpenAI compatible base URL from config file (e.g., for OpenRouter)."""
    keys_data = _load_keys_config()
    return keys_data.get("base_url")


def get_host() -> str:
    """Get BlueOS host from config file or default to HOST constant."""
    keys_data = _load_keys_config()
    return keys_data.get("host", HOST)


def get_port() -> int:
    """Get BlueOS port from config file or default to PORT constant."""
    keys_data = _load_keys_config()
    return keys_data.get("port", PORT)
