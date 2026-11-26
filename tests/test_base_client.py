from unittest.mock import patch

import pytest

from blue_cli.base_client import BluesoundBaseClient


@pytest.fixture
def client() -> BluesoundBaseClient:
    return BluesoundBaseClient("127.0.0.1", 11000)


def test_play_requests_playback_without_a_song_id(client: BluesoundBaseClient) -> None:
    with patch.object(BluesoundBaseClient, "_make_request") as request:
        client.play()

    request.assert_called_once_with("Play")


def test_stop_requests_stop(client: BluesoundBaseClient) -> None:
    with patch.object(BluesoundBaseClient, "_make_request") as request:
        client.stop()

    request.assert_called_once_with("Stop")


def test_pause_toggles_playback(client: BluesoundBaseClient) -> None:
    with patch.object(BluesoundBaseClient, "_make_request") as request:
        client.pause()

    request.assert_called_once_with("Pause", params={"toggle": 1})
