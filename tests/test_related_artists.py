from unittest.mock import Mock, patch

import pytest

from blue_cli.errors import BlueOSError
from blue_cli.tidal_service import TidalService

SIMILAR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<artists service="Tidal">
  <art artistid="10116" image="/Artwork?service=Tidal&amp;artistpicture=abc"
       artistpicture="abc" similarstationid="Tidal:radio:artist/10116">The Proclaimers</art>
  <art artistid="1736" image="/Artwork?service=Tidal&amp;artistpicture=def"
       artistpicture="def" isFavourite="1">Dido</art>
  <art artistid="9999">  </art>
</artists>
"""

EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<artists service="Tidal"></artists>
"""


def _service() -> TidalService:
    return TidalService("localhost", 11000)


def _similar_artists(service: TidalService, artist_id: str = "14887"):
    # Bypass the disk cache so each test parses the patched response.
    return TidalService.get_similar_artists.__wrapped__(service, artist_id)


def test_similar_artists_request_uses_related_category():
    service = _service()
    with patch.object(service, "_make_request", return_value=SIMILAR_XML) as request:
        _similar_artists(service)

    request.assert_called_once_with("Artists?service=Tidal&artistid=14887&category=related")


def test_similar_artists_are_parsed_from_xml():
    service = _service()
    with patch.object(service, "_make_request", return_value=SIMILAR_XML):
        similar = _similar_artists(service)

    assert similar == [
        {
            "id": "10116",
            "name": "The Proclaimers",
            "similarstationid": "Tidal:radio:artist/10116",
            "isFavourite": False,
        },
        {
            "id": "1736",
            "name": "Dido",
            "similarstationid": "Tidal:radio:artist/1736",
            "isFavourite": True,
        },
    ]


def test_similar_station_id_falls_back_to_artist_radio():
    service = _service()
    xml = '<artists service="Tidal"><art artistid="42">Artist</art></artists>'
    with patch.object(service, "_make_request", return_value=xml):
        similar = _similar_artists(service)

    assert similar[0]["similarstationid"] == "Tidal:radio:artist/42"


def test_no_similar_artists_returns_empty_list():
    service = _service()
    with patch.object(service, "_make_request", return_value=EMPTY_XML):
        assert _similar_artists(service) == []


def test_resolve_artist_uses_current_track_when_name_is_missing():
    service = _service()
    status = {"status": {"artistid": "14887", "artist": "The Corrs"}}
    with patch.object(service, "get_status", return_value=status):
        assert service.resolve_artist("") == ("14887", "The Corrs")


def test_resolve_artist_prefers_exact_name_match():
    service = _service()
    matches = [{"id": "1", "name": "The Corrs Tribute"}, {"id": "14887", "name": "The Corrs"}]
    with patch.object(service, "search_artists", return_value=matches):
        assert service.resolve_artist("the corrs") == ("14887", "The Corrs")


def test_resolve_artist_raises_when_nothing_matches():
    service = _service()
    with patch.object(service, "search_artists", return_value=[]):
        with pytest.raises(BlueOSError, match="No Tidal artist found"):
            service.resolve_artist("Nobody")


def test_related_queue_adds_random_album_per_picked_artist():
    service = _service()
    similar = [
        {
            "id": "10116",
            "name": "The Proclaimers",
            "similarstationid": "Tidal:radio:artist/10116",
            "isFavourite": False,
        }
    ]
    album = {
        "id": "album-1",
        "title": "Sunshine on Leith",
        "date": "1988-01-01",
        "artist": "The Proclaimers",
        "tracks": "12",
        "quality": "cd",
    }
    with (
        patch.object(service, "resolve_artist", return_value=("14887", "The Corrs")),
        patch.object(service, "get_similar_artists", return_value=similar),
        patch.object(service, "select_artist", return_value=similar) as select,
        patch.object(service, "get_albums", return_value=[album]),
        patch.object(service, "add_album_to_queue") as add_album,
    ):
        service.cli_related_artists("", queue=True)

    select.assert_called_once_with(similar, multi=True)
    add_album.assert_called_once_with("album-1")


def test_related_queue_with_top_tracks_does_not_add_albums():
    service = _service()
    similar = [
        {
            "id": "10116",
            "name": "The Proclaimers",
            "similarstationid": "Tidal:radio:artist/10116",
            "isFavourite": False,
        }
    ]
    with (
        patch.object(service, "resolve_artist", return_value=("14887", "The Corrs")),
        patch.object(service, "get_similar_artists", return_value=similar),
        patch.object(service, "select_artist", return_value=similar),
        patch.object(service, "add_top_tracks_to_queue") as add_tracks,
        patch.object(service, "add_album_to_queue") as add_album,
    ):
        service.cli_related_artists("", queue=True, tracks=True)

    add_tracks.assert_called_once_with("10116")
    add_album.assert_not_called()


def test_related_radio_plays_the_selected_station():
    service = _service()
    similar = [
        {
            "id": "1736",
            "name": "Dido",
            "similarstationid": "Tidal:radio:artist/1736",
            "isFavourite": True,
        }
    ]
    with (
        patch.object(service, "resolve_artist", return_value=("14887", "The Corrs")),
        patch.object(service, "get_similar_artists", return_value=similar),
        patch.object(service, "select_artist", return_value=similar[0]),
        patch.object(service, "play_artist_radio") as play_radio,
        patch.object(service, "add_album_to_queue") as add_album,
    ):
        service.cli_related_artists("", radio=True)

    play_radio.assert_called_once_with("Tidal:radio:artist/1736")
    add_album.assert_not_called()


def test_related_listing_does_not_queue_or_play():
    service = _service()
    similar = [
        {
            "id": "1736",
            "name": "Dido",
            "similarstationid": "Tidal:radio:artist/1736",
            "isFavourite": True,
        }
    ]
    with (
        patch.object(service, "resolve_artist", return_value=("14887", "The Corrs")),
        patch.object(service, "get_similar_artists", return_value=similar),
        patch.object(service, "select_artist") as select,
        patch.object(service, "play_artist_radio") as play_radio,
        patch.object(service, "add_album_to_queue") as add_album,
    ):
        service.cli_related_artists("")

    select.assert_not_called()
    play_radio.assert_not_called()
    add_album.assert_not_called()


def test_play_artist_radio_quotes_station_id():
    service = _service()
    with patch.object(service, "_make_request", return_value="OK") as request:
        service.play_artist_radio("Tidal:radio:artist/14887")

    request.assert_called_once_with("Play?url=Tidal%3Aradio%3Aartist%2F14887")


def test_add_top_tracks_rejects_xml_error():
    service = _service()
    with patch.object(service, "_make_request", return_value='<error message="nope"/>'):
        with pytest.raises(ValueError, match="Player rejected top tracks"):
            service.add_top_tracks_to_queue(14887)


def test_select_artist_returns_none_when_cancelled(monkeypatch):
    service = _service()
    monkeypatch.setattr(
        "blue_cli.tidal_service.FzfPrompt",
        lambda _options: Mock(prompt=Mock(side_effect=IndexError)),
    )

    assert service.select_artist([{"id": "1", "name": "Artist"}]) is None
    assert service.select_artist([{"id": "1", "name": "Artist"}], multi=True) == []


def test_select_artist_maps_picked_lines_back_by_id(monkeypatch):
    service = _service()
    artists = [{"id": "1", "name": "First"}, {"id": "2", "name": "Second"}]
    captured = {}

    class FakeFzfPrompt:
        def __init__(self, options):
            captured["options"] = options

        def prompt(self, lines):
            return ["2\tSecond"]

    monkeypatch.setattr("blue_cli.tidal_service.FzfPrompt", FakeFzfPrompt)

    assert service.select_artist(artists) == artists[1]
    assert "--multi" not in captured["options"]
    assert service.select_artist(artists, multi=True) == [artists[1]]
    assert "--multi" in captured["options"]


def test_resolve_artist_reports_cancelled_selection():
    service = _service()
    matches = [{"id": "1", "name": "Dido A"}, {"id": "2", "name": "Dido B"}]
    with (
        patch.object(service, "search_artists", return_value=matches),
        patch.object(service, "select_artist", return_value=None),
    ):
        with pytest.raises(BlueOSError, match="No artist selected"):
            service.resolve_artist("Dido")
