import json
import os
from pathlib import Path

# Default Server info, change these values to match yours.
HOST = "192.168.88.15"
PORT = 11000

__version__ = "1.0.0"
__author__ = "IbeeX"

MEDIA_LOCATION = "Library"

home = Path.home()
cache_path = home / ".cache" / "blue"
config_path = home / ".config" / "blue_cli"

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


def get_base_url() -> str | None:
    """Get OpenAI compatible base URL from config file (e.g., for OpenRouter)."""
    keys_data = _load_keys_config()
    return keys_data.get("base_url")
