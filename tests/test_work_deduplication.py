"""Work-level queue planning using resolved catalogue tracks, without network calls."""

import json
import re
from unittest.mock import Mock, patch

import pytest

from blue_cli.ai_service import AIRecommendationService, AIResponse, Recommendation, SearchResult
from blue_cli.tidal_service import TidalService
from blue_cli.work_identity import work_keys


@pytest.fixture
def service():
    with patch("blue_cli.ai_service.TidalService"):
        instance = AIRecommendationService(host="example.com", port=11000)
    instance.ai_client.make_request = Mock(return_value=AIResponse("null", True))
    return instance


def tracks(album_id, works):
    return [
        {"id": f"Tidal:{album_id}-{index}-{movement}", "title": f"{work}: {movement}. Allegro"}
        for index, work in enumerate(works)
        for movement in range(1, 4)
    ]


def catalogue(service, releases):
    contents = {album_id: tracks(album_id, works) for album_id, _, works in releases}
    results = iter(
        [
            SearchResult(album_id, "Performer", title, "2020", len(contents[album_id]))
            for album_id, title, _ in releases
        ]
    )
    service.search_service.find_best_match = Mock(
        side_effect=lambda *args, **kwargs: next(results, None)
    )
    service.tidal_service.get_album_tracks_by_id.side_effect = contents.__getitem__
    return contents


@pytest.mark.parametrize("test_mode", [False, True])
def test_overlapping_albums_are_replaced_by_nonoverlapping_whole_albums(service, test_mode):
    works = [f"Beethoven: Piano Concerto No. {number}" for number in range(1, 6)]
    recommendations = [Recommendation("Performer", work, work) for work in works]
    catalogue(
        service,
        [
            (13, "Beethoven: Piano Concertos Nos. 1 & 3", [works[0], works[2]]),
            (12, "Beethoven: Piano Concertos No. 1 & No. 2", [works[0], works[1]]),
            (2, works[1], [works[1]]),
            (34, "Beethoven: Piano Concertos Nos.3 & 4", [works[2], works[3]]),
            (4, works[3], [works[3]]),
            (5, works[4], [works[4]]),
        ],
    )
    service.ai_client.make_request.side_effect = [
        AIResponse('{"candidate_id": "2"}', True),
        AIResponse('{"candidate_id": "4"}', True),
    ]
    resolved = service._process_prompt_recommendations(
        recommendations, "all five concertos", test_mode
    )
    assert len(resolved) == 4
    assert set().union(*(work_keys(rec.work) for rec in resolved)) == {
        ("beethoven", "piano concerto", str(number)) for number in range(1, 6)
    }
    if test_mode:
        service.tidal_service.add_album_to_queue.assert_not_called()
    else:
        assert [
            call.args[0] for call in service.tidal_service.add_album_to_queue.call_args_list
        ] == [13, 2, 4, 5]
    service.tidal_service.add_song_to_queue.assert_not_called()
    assert "selected works" not in resolved[1].album
    assert service.ai_client.make_request.call_count == 2


@pytest.mark.parametrize(
    "work",
    [
        "Mozart: Violin Concerto No. 3",
        "Schubert: Piano Sonata No. 21",
        "Brahms: String Quartet No. 1",
        "Haydn: Symphony No. 104",
    ],
)
def test_work_planning_is_not_specific_to_one_composer_or_work_type(service, work):
    catalogue(service, [(1, work, [work])])
    assert (
        len(
            service._process_prompt_recommendations(
                [Recommendation("Artist", work, work)], "add work"
            )
        )
        == 1
    )
    service.tidal_service.add_album_to_queue.assert_called_once_with(1)


def test_no_nonoverlapping_whole_album_solution_does_not_fall_back_to_tracks(service, capsys):
    works = [f"Beethoven: Piano Concerto No. {number}" for number in range(1, 6)]
    catalogue(
        service,
        [
            (13, "Beethoven: Piano Concertos Nos. 1 & 3", [works[0], works[2]]),
            (12, "Beethoven: Piano Concertos Nos. 1 & 2", [works[0], works[1]]),
        ],
    )
    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", work, work) for work in works], "all five concertos"
    )
    assert resolved == []
    service.tidal_service.add_album_to_queue.assert_not_called()
    service.tidal_service.add_song_to_queue.assert_not_called()
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "repeats already-selected works" in " ".join(output.split())
    assert "Queue unchanged" in " ".join(output.split())


def test_rejected_album_ids_are_excluded_from_search_and_candidates(service):
    work = "Mozart: Violin Concerto No. 3"
    service.tidal_service.search_albums.return_value = [
        {"id": str(album_id), "artist": "Artist", "title": work, "date": "2020", "tracks": 3}
        for album_id in [1, 2]
    ]
    result = service.search_service.find_best_match(
        Recommendation("Artist", work, work), excluded_ids={1}
    )
    assert result is not None and result.id == 2
    assert (
        service.search_service.find_best_match(
            Recommendation("Artist", "Unavailable", work), excluded_ids={1, 2}
        )
        is None
    )
    assert service.search_service.candidates == []


def test_album_track_reader_retains_song_ids_for_singleton_xml():
    tidal = TidalService(host="example.com", port=11000)
    with (
        patch.object(tidal, "_make_request", return_value="xml"),
        patch.object(
            tidal,
            "_parse_xml",
            return_value={
                "songs": {"album": {"song": {"songid": "Tidal:123", "title": "Movement"}}}
            },
        ),
    ):
        result = TidalService.get_album_tracks_by_id.__wrapped__(tidal, 1)
    assert len(result) == 1
    assert result[0]["id"] == "Tidal:123"


@pytest.mark.parametrize(
    "xml",
    [
        '<error message="Unavailable album"/>',
        "<addsong><error>Unavailable album</error></addsong>",
    ],
)
def test_http_success_with_xml_error_is_not_reported_as_album_added(xml):
    tidal = TidalService(host="example.com", port=11000)
    with patch.object(tidal, "_make_request", return_value=xml):
        with pytest.raises(ValueError, match="Player rejected album"):
            tidal.add_album_to_queue(42)


def test_album_add_accepts_successful_xml_response():
    tidal = TidalService(host="example.com", port=11000)
    with patch.object(tidal, "_make_request", return_value='<addsong status="OK"/>') as request:
        tidal.add_album_to_queue(42)
    request.assert_called_once_with("Add?service=Tidal&albumid=42&playnow=-1&where=last")


def test_identity_separates_composers_and_instruments():
    assert work_keys("Mozart: Piano Concerto No. 3") != work_keys("Beethoven: Piano Concerto No. 3")
    assert work_keys("Mozart: Piano Concerto No. 3") != work_keys("Mozart: Violin Concerto No. 3")
    assert work_keys("Ludwig van Beethoven: Piano Concertos Nos.3 & 4") == {
        ("beethoven", "piano concerto", "3"),
        ("beethoven", "piano concerto", "4"),
    }


def test_catalogue_aliases_come_from_metadata_not_composer_specific_tables(service):
    work = "Mozart: Piano Concerto No. 21 K. 467"
    catalogue(service, [(1, work, ["Piano Concerto in C Major, K. 467"])])
    assert (
        len(
            service._process_prompt_recommendations(
                [Recommendation("Artist", work, work)], "add work"
            )
        )
        == 1
    )
    service.ai_client.make_request.assert_not_called()


def test_missing_coverage_leaves_queue_unchanged(service, capsys):
    one = "Brahms: Piano Concerto No. 1"
    two = "Brahms: Piano Concerto No. 2"
    catalogue(service, [(1, one, [one]), (2, one, [one])])
    assert (
        service._process_prompt_recommendations(
            [Recommendation("Artist", one, one), Recommendation("Artist", two, two)],
            "both concertos",
        )
        == []
    )
    service.tidal_service.add_album_to_queue.assert_not_called()
    service.tidal_service.add_song_to_queue.assert_not_called()
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "Queue unchanged" in " ".join(output.split())


def test_clarification_replacement_is_checked_against_actual_tracks(service):
    work = "Beethoven: Piano Concerto No. 3 Op. 37"
    service.search_service.find_best_match = Mock(
        side_effect=[
            None,
            SearchResult(1, "Artist", "Beethoven: Piano Concertos Nos. 1 & 3", "2020", 6),
            SearchResult(2, "Artist", work, "2020", 3),
        ]
    )
    service.ai_client.make_request.side_effect = [
        AIResponse(
            json.dumps({"artist": "Artist", "album": "Beethoven: Piano Concertos Nos. 1 & 3"}), True
        ),
        AIResponse('{"candidate_id": "2"}', True),
    ]
    actual = {
        1: tracks(1, ["Beethoven: Piano Concerto No. 1", "Piano Concerto in C minor, Op. 37"]),
        2: tracks(2, ["Piano Concerto in C minor, Op. 37"]),
    }
    service.tidal_service.get_album_tracks_by_id.side_effect = actual.__getitem__
    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", "Unavailable", work)], "third concerto"
    )
    assert len(resolved) == 1
    service.tidal_service.add_song_to_queue.assert_not_called()
    service.tidal_service.add_album_to_queue.assert_called_once_with(2)


@pytest.mark.parametrize("bad", [False, True])
def test_ambiguous_tracks_use_validated_llm_identification(service, bad):
    work = "Ravel: Piano Concerto No. 1"
    catalogue(service, [(1, work, [work])])
    ambiguous = [
        {"id": f"Tidal:{index}", "title": title}
        for index, title in enumerate(["I. Allegro", "II. Adagio", "III. Presto"])
    ]
    service.tidal_service.get_album_tracks_by_id.side_effect = None
    service.tidal_service.get_album_tracks_by_id.return_value = ambiguous
    service.ai_client.make_request.return_value = AIResponse(
        json.dumps(
            [{"id": "invented" if bad else track["id"], "work": work} for track in ambiguous]
        ),
        True,
    )
    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", work, work)], "add concerto"
    )
    assert len(resolved) == (0 if bad else 1)
    assert service.ai_client.make_request.call_count == (2 if bad else 1)
    service.tidal_service.add_song_to_queue.assert_not_called()
    if bad:
        service.tidal_service.add_album_to_queue.assert_not_called()


def test_explicit_multiple_interpretations_are_not_suppressed(service):
    work = "Brahms: Piano Concerto No. 1"
    catalogue(service, [(1, work, [work]), (2, work, [work])])
    recommendations = [
        Recommendation("Artist A", work, work),
        Recommendation("Artist B", work, work),
    ]
    assert (
        len(
            service._process_prompt_recommendations(recommendations, "compare different recordings")
        )
        == 2
    )
    assert service.tidal_service.add_album_to_queue.call_count == 2


def test_incomplete_track_metadata_cannot_mutate_queue(service):
    work = "Mozart: Piano Concerto No. 21"
    catalogue(service, [(1, work, [work])])
    service.tidal_service.get_album_tracks_by_id.side_effect = None
    service.tidal_service.get_album_tracks_by_id.return_value = tracks(1, [work])[:2]
    assert (
        service._process_prompt_recommendations(
            [Recommendation("Artist", work, work)], "add concerto"
        )
        == []
    )
    service.tidal_service.add_album_to_queue.assert_not_called()
    service.tidal_service.add_song_to_queue.assert_not_called()
