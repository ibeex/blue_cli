import json
from datetime import date, timedelta
from unittest.mock import Mock

from blue_cli.tidal_service import TidalService, _deduplicate_album_qualities


def _album(album_id: str, release_date: date) -> dict[str, str]:
    return {"id": album_id, "date": release_date.isoformat()}


def test_deduplicate_album_qualities_prefers_hd_over_cd_and_other_qualities():
    cd = {
        "id": "cd",
        "artist": "Artist",
        "title": "Album",
        "date": "2026-08-12",
        "tracks": "10",
        "quality": "cd",
    }
    hd = {**cd, "id": "hd", "quality": "hd"}
    other_quality = {**cd, "id": "other", "quality": "mqa"}

    assert _deduplicate_album_qualities([other_quality, cd, hd]) == [hd]


def test_recent_album_selector_adds_on_enter_without_closing_fzf(monkeypatch):
    options = []

    class FakeFzfPrompt:
        def __init__(self, option):
            options.append(option)

        def prompt(self, _albums):
            return []

    monkeypatch.setattr("blue_cli.tidal_service.FzfPrompt", FakeFzfPrompt)
    service = TidalService("localhost", 11000)
    album = {
        "id": "recent",
        "artist": "Artist",
        "title": "Album",
        "date": "2026-08-12",
        "tracks": "10",
        "quality": "hd",
    }

    assert service.add_recent_albums_with_fzf([album]) == []
    assert "enter:execute-silent(" in options[0]
    assert "+down" in options[0]
    assert "esc: finish" in options[0]


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
    service.add_recent_albums_with_fzf = Mock(return_value=["Artist: Album"])
    monkeypatch.setattr("blue_cli.tidal_service.cache_path", tmp_path)

    service.cli_search_recent_favorite_albums(30)

    assert json.loads((tmp_path / "albums.json").read_text()) == albums
    service.add_recent_albums_with_fzf.assert_called_once_with(albums)
