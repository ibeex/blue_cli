"""Tests for configuration fallbacks and overrides."""

from unittest.mock import patch

import pytest

from blue_cli import config


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ({}, config.AI_MAX_COMPLETION_TOKENS),
        ({"max_completion_tokens": 32000}, 32000),
        ({"max_completion_tokens": "24000"}, 24000),
        ({"max_completion_tokens": 0}, config.AI_MAX_COMPLETION_TOKENS),
        ({"max_completion_tokens": -5}, config.AI_MAX_COMPLETION_TOKENS),
        ({"max_completion_tokens": True}, config.AI_MAX_COMPLETION_TOKENS),
        ({"max_completion_tokens": "lots"}, config.AI_MAX_COMPLETION_TOKENS),
    ],
)
def test_max_completion_tokens_override(stored, expected):
    with patch.object(config, "_load_keys_config", return_value=stored):
        assert config.get_max_completion_tokens() == expected
