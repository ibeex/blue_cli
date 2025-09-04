import json
import os
from pathlib import Path

# Default Server info, change these values to match yours.
HOST = "192.168.88.15"
PORT = 11000

__version__ = "1.0.0"
__author__ = "IbeeX"

MEDIA_LOCATION = "Library"
AI_MODEL = "gpt-5"

home = Path.home()
cache_path = home / ".cache" / "blue"

if not cache_path.exists():
    cache_path.mkdir(parents=True)


def get_openai_key() -> str | None:
    """Get OpenAI API key from environment or LLM keys file."""
    # Try environment variable first
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key

    # Try LLM keys file
    keys_file = home / "Library/Application Support/io.datasette.llm/keys.json"
    if keys_file.exists():
        try:
            with open(keys_file) as f:
                keys_data = json.load(f)
                return keys_data.get("openai")
        except (OSError, json.JSONDecodeError):
            pass

    return None
