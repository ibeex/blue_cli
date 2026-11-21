"""Reusable BlueOS client library plus the optional command-line interface."""

from .base_client import BluesoundBaseClient, PlayerState, Song
from .errors import BlueOSError

__all__ = ["BlueOSError", "BluesoundBaseClient", "PlayerState", "Song"]


def __getattr__(name: str):
    # Import the CLI lazily so library users do not need fzf or the CLI-only dependencies.
    if name == "cli":
        from .blue_cli import cli

        return cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
