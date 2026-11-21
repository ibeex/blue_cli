from unittest.mock import Mock

from blue_cli.tidal_service import TidalService


def _album(album_id: str) -> dict[str, str]:
    return {
        "id": album_id,
        "title": "Test Album",
        "date": "2024-01-01",
        "artist": "Test Artist",
        "tracks": "10",
        "quality": "cd",
    }


def test_queue_random_favorite_albums_uses_random_favorite_selection() -> None:
    service = TidalService("localhost", 11000)
    service.search_artists = Mock(return_value=[{"id": "artist-1", "name": "Test Artist"}])
    service.get_albums = Mock(return_value=[_album("album-1")])
    service.add_album_to_queue = Mock()

    albums = service.queue_random_favorite_albums(1)

    assert albums == ["Test Artist: Test Album"]
    service.add_album_to_queue.assert_called_once_with("album-1")


def test_queue_random_favorite_albums_skips_artists_without_albums() -> None:
    service = TidalService("localhost", 11000)
    service.search_artists = Mock(return_value=[{"id": "artist-1", "name": "Test Artist"}])
    service.get_albums = Mock(return_value=[])
    service.add_album_to_queue = Mock()

    assert service.queue_random_favorite_albums() == []
    service.add_album_to_queue.assert_not_called()
