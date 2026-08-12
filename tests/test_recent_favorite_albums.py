import json
from datetime import date, timedelta
from unittest.mock import Mock

from blue_cli.tidal_service import TidalService


def _album(album_id: str, release_date: date) -> dict[str, str]:
    return {"id": album_id, "date": release_date.isoformat()}


def test_recent_favorite_albums_excludes_classical_and_old_releases():
    service = TidalService("localhost", 11000)
    today = date.today()
    service.search_artists = Mock(
        return_value=[
            {"id": "classical", "name": "Ludwig van Beethoven"},
            {"id": "other", "name": "Agnes Obel"},
        ]
    )
    service.get_albums = Mock(
        return_value=[
            _album("agnes-old", today - timedelta(days=31)),
            _album("agnes-new", today - timedelta(days=1)),
            _album("agnes-new", today - timedelta(days=1)),
            {"id": "unknown-date", "date": "unknown"},
        ]
    )

    albums = service.get_recent_favorite_albums(30)

    assert albums == [_album("agnes-new", today - timedelta(days=1))]
    service.get_albums.assert_called_once_with("other")


def test_recent_favorite_albums_can_search_only_classical_artists():
    service = TidalService("localhost", 11000)
    today = date.today()
    service.search_artists = Mock(
        return_value=[
            {"id": "classical", "name": "Ludwig van Beethoven"},
            {"id": "other", "name": "Agnes Obel"},
        ]
    )
    service.get_albums = Mock(return_value=[_album("classical-new", today)])

    albums = service.get_recent_favorite_albums(30, classical_only=True)

    assert albums == [_album("classical-new", today)]
    service.get_albums.assert_called_once_with("classical")


def test_recent_album_search_caches_results_for_fzf_preview(tmp_path, monkeypatch):
    service = TidalService("localhost", 11000)
    albums = [_album("recent", date.today())]
    service.get_recent_favorite_albums = Mock(return_value=albums)
    service.select_album = Mock(return_value=("recent", "selected album"))
    service.add_album_to_queue = Mock()
    monkeypatch.setattr("blue_cli.tidal_service.cache_path", tmp_path)

    service.cli_search_recent_favorite_albums(30)

    assert json.loads((tmp_path / "albums.json").read_text()) == albums
    service.add_album_to_queue.assert_called_once_with("recent")
