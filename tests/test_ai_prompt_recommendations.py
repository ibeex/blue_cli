"""Offline tests for custom queries; no paid AI calls or real queue changes."""

import json
import re
from unittest.mock import Mock, patch

import httpx
import openai
import pytest
from click.testing import CliRunner

from blue_cli.ai_service import (
    AIRecommendationService,
    AIResponse,
    PromptTemplates,
    Recommendation,
    RecommendationParser,
    ResponseType,
    SearchError,
    SearchResult,
)
from blue_cli.blue_cli import cli
from blue_cli.tidal_service import TidalService


@pytest.fixture
def service():
    with patch("blue_cli.ai_service.TidalService"):
        instance = AIRecommendationService(host="example.com", port=11000)
    instance.ai_client.make_request = Mock()
    instance._generate_prompt_explanation = Mock()
    return instance


def response(data) -> AIResponse:
    return AIResponse(content=json.dumps(data), success=True)


def album_result(album_id: int = 1, title: str = "Correct Title") -> SearchResult:
    return SearchResult(album_id, "Recording Artist", title, "2020-01-01", 4)


def mock_symphony_tracks(service, albums):
    service.tidal_service.get_album_tracks_by_id.side_effect = lambda album_id: [
        {"id": f"Tidal:{album_id}{index}", "title": f"{work}: Movement {index + 1}"}
        for index, work in enumerate(albums[album_id])
    ]


@pytest.mark.parametrize("count", [1, 4, 7])
def test_custom_query_accepts_requested_quantity(service, count):
    recommendations = [
        {"artist": "Recording Artist", "album": f"Album {index}"} for index in range(count)
    ]
    service.ai_client.make_request.return_value = response(recommendations)
    service.search_service.find_best_match = Mock(
        side_effect=[album_result(index, f"Album {index}") for index in range(count)]
    )
    prompt = f"give me {count} albums"

    assert service.get_prompt_recommendations_and_enqueue(prompt) == count
    assert service.tidal_service.add_album_to_queue.call_count == count
    request, response_type = service.ai_client.make_request.call_args.args
    assert prompt in request
    assert "Honor the user's requested quantity" in request
    assert response_type == ResponseType.RECOMMENDATION


def test_berlin_trilogy_remasters_enqueue_without_ai_clarification(service):
    titles = ["Low", '"Heroes"', "Lodger"]
    service.ai_client.make_request.return_value = response(
        [{"artist": "David Bowie", "album": title} for title in titles]
    )
    catalogue = [
        {
            "id": str(index),
            "artist": "David Bowie",
            "title": f"{title} (2017 Remaster)",
            "date": "2017-01-01",
            "tracks": "10",
        }
        for index, title in enumerate(titles, start=1)
    ]
    service.tidal_service.search_albums.return_value = catalogue

    assert service.get_prompt_recommendations_and_enqueue("add Bowie berlin trilogy albums") == 3
    assert service.tidal_service.add_album_to_queue.call_count == 3
    assert service.tidal_service.search_albums.call_count == 3
    service.ai_client.make_request.assert_called_once()


def test_ai_command_uses_selected_player_for_prompt_queries():
    with (
        patch("blue_cli.blue_cli.BlueSound") as player_class,
        patch("blue_cli.blue_cli.AIRecommendationService") as ai_class,
    ):
        player_class.return_value.host = "chosen-player"
        player_class.return_value.port = 12000
        result = CliRunner().invoke(
            cli,
            ["ai", "--host", "chosen-player", "--port", "12000", "--test", "four albums"],
        )

    assert result.exit_code == 0, result.output
    ai_class.assert_called_once_with(host="chosen-player", port=12000, model=None, verbose=False)
    ai_class.return_value.get_prompt_recommendations_test_mode.assert_called_once_with(
        "four albums"
    )
    player_class.return_value.curent_song_id.assert_not_called()


def test_empty_tidal_search_returns_without_exiting():
    tidal = TidalService("localhost", 11000)
    tidal._make_request = Mock()
    tidal._parse_xml = Mock(return_value={"albums": {"album": []}})

    assert tidal.search_albums("Unavailable") == []


def test_beethoven_catalogue_variants_are_resolved_using_real_candidates(service):
    query = "give me first 4 symphonies by Beethoven"
    recommendations = [
        {
            "artist": "Minnesota Orchestra, Osmo Vänskä",
            "album": "Beethoven: Symphonies Nos. 1 & 6 'Pastoral'",
            "work": "Beethoven Symphony No. 1 Op. 21",
        },
        {
            "artist": "Minnesota Orchestra, Osmo Vänskä",
            "album": "Beethoven: Symphonies Nos. 2 & 7",
            "work": "Beethoven Symphony No. 2 Op. 36",
        },
        {
            "artist": "Pittsburgh Symphony Orchestra, Manfred Honeck",
            "album": "Beethoven: Symphony No. 3 'Eroica' - Strauss: Horn Concerto No. 1",
            "work": "Beethoven Symphony No. 3 Op. 55",
        },
        {
            "artist": "Bayerisches Staatsorchester, Carlos Kleiber",
            "album": "Beethoven: Symphony No. 4 in B-Flat Major, Op. 60",
            "work": "Beethoven Symphony No. 4 Op. 60",
        },
    ]
    # Offline catalogue fixtures reproduce metadata differences, not verified live releases.
    titles = [
        "Beethoven: Symphony No. 1, Op. 21",
        "Beethoven: Symphony No. 2, Op. 36",
        "Beethoven: Symphony No. 3, Eroica / Strauss: Horn Concerto No. 1",
        recommendations[3]["album"],
    ]
    artists = [
        "Osmo Vanska",
        "Minnesota Orchestra",
        "Manfred Honeck",
        "Bayerisches Staatsorchester",
    ]
    catalogue = [
        {
            "id": str(index),
            "artist": artist,
            "title": title,
            "tracks": "4",
            "date": "2020-01-01",
        }
        for index, (artist, title) in enumerate(zip(artists, titles, strict=True), start=1)
    ]
    catalogue.append({**catalogue[0], "id": "99", "title": "Beethoven: Symphony No. 9"})
    service.tidal_service.search_albums.return_value = catalogue
    service.ai_client.make_request.side_effect = [
        response(recommendations),
        response({"candidate_id": "1"}),
        response({"candidate_id": "2"}),
    ]

    mock_symphony_tracks(
        service, {number: [f"Beethoven: Symphony No. {number}"] * 4 for number in range(1, 5)}
    )
    assert service.get_prompt_recommendations_and_enqueue(query) == 4
    assert [call.args[0] for call in service.tidal_service.add_album_to_queue.call_args_list] == [
        1,
        2,
        3,
        4,
    ]
    calls = service.ai_client.make_request.call_args_list
    # No. 2, 3 and 4 resolve from catalogue metadata; only No. 1 needs clarification.
    assert len(calls) == 2
    clarification = calls[1]
    assert "Beethoven Symphony No. 1" in clarification.args[0]
    assert titles[0] in clarification.args[0]
    assert '"id": "99"' not in clarification.args[0]
    assert clarification.args[1] == ResponseType.CLARIFICATION


@pytest.mark.parametrize("selected_id", ["999", True, None, [1]])
def test_candidate_id_must_belong_to_actual_results(service, selected_id):
    service.search_service.find_best_match = Mock(return_value=None)
    service.search_service.candidates = [album_result()]
    service.ai_client.make_request.return_value = response({"candidate_id": selected_id})

    assert (
        service._resolve_prompt_recommendation(Recommendation("Artist", "Album"), "music") is None
    )
    service.tidal_service.add_album_to_queue.assert_not_called()


def test_candidate_selection_accepts_json_fences_in_test_mode(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.search_service.candidates = [album_result()]
    service.ai_client.make_request.return_value = AIResponse(
        '```json\n{"candidate_id": "1"}\n```', True
    )

    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", "Album")], "music", test_mode=True
    )

    assert resolved == [Recommendation("Recording Artist", "Correct Title")]
    service.tidal_service.add_album_to_queue.assert_not_called()


def test_candidate_selection_recovers_json_embedded_in_prose(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.search_service.candidates = [album_result()]
    service.ai_client.make_request.return_value = AIResponse(
        'I recommend the first one: {"candidate_id": "1"} - enjoy!', True
    )

    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", "Album")], "music", test_mode=True
    )

    assert resolved == [Recommendation("Recording Artist", "Correct Title")]


def test_composer_transliteration_resolves_without_clarification(service):
    recommendation = Recommendation(
        "Sviatoslav Richter",
        "Rachmaninov: Piano Concerto No. 2",
        "Rachmaninoff Piano Concerto No. 2 Op. 18",
    )
    service.tidal_service.search_albums.return_value = [
        {
            "id": "5",
            "artist": "Sviatoslav Richter",
            "title": "Rachmaninov: Piano Concerto No. 2, Op. 18",
            "date": "2020-01-01",
            "tracks": "3",
        }
    ]

    result = service.search_service.find_best_match(recommendation)

    assert result is not None and result.id == 5
    service.ai_client.make_request.assert_not_called()


def test_unverifiable_work_skips_track_validation_in_mixed_request(service):
    recognized = Recommendation(
        "Artist", "Beethoven: Symphony No. 1", "Beethoven Symphony No. 1 Op. 21"
    )
    ballet = Recommendation(
        "Artist", "Stravinsky: The Rite of Spring", "Stravinsky The Rite of Spring"
    )
    service.search_service.find_best_match = Mock(
        side_effect=[
            album_result(1, "Beethoven: Symphony No. 1"),
            album_result(2, "Stravinsky: The Rite of Spring"),
        ]
    )
    service.tidal_service.get_album_tracks_by_id.return_value = [
        {"id": f"Tidal:{index}", "title": "Symphony No. 1: Movement"} for index in range(4)
    ]

    resolved = service._process_prompt_recommendations(
        [recognized, ballet], "add these", test_mode=True
    )

    assert len(resolved) == 2
    # Only the recognised symphony needs its tracks read; the ballet is accepted by title.
    service.tidal_service.get_album_tracks_by_id.assert_called_once_with(1)


def test_fuzzy_request_queues_partial_coverage(service, capsys):
    one = Recommendation("Artist", "Brahms: Piano Concerto No. 1", "Brahms Piano Concerto No. 1")
    two = Recommendation("Artist", "Brahms: Piano Concerto No. 2", "Brahms Piano Concerto No. 2")
    service.search_service.find_best_match = Mock(
        side_effect=[album_result(1, "Brahms: Piano Concerto No. 1"), None]
    )
    service.ai_client.make_request.return_value = response(None)
    service.tidal_service.get_album_tracks_by_id.return_value = [
        {"id": f"Tidal:{index}", "title": "Piano Concerto No. 1: Movement"} for index in range(4)
    ]

    resolved = service._process_prompt_recommendations(
        [one, two], "10 best romantic albums", test_mode=True
    )

    assert len(resolved) == 1
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "Partial work coverage" in output


def test_extract_json_recovers_values_from_prose():
    from blue_cli.ai_service import extract_json

    assert extract_json('Here:\n```json\n{"candidate_id": "1"}\n```\nDone') == {"candidate_id": "1"}
    assert extract_json('Use [{"artist": "A", "album": "B"}] now') == [
        {"artist": "A", "album": "B"}
    ]
    assert extract_json(None) is None
    assert extract_json("") is None
    assert extract_json("no json here") is None


def test_broader_search_uses_requested_work_and_retains_candidates(service):
    recommendation = Recommendation(
        "Minnesota Orchestra",
        "Beethoven: Symphonies Nos. 1 & 6 'Pastoral'",
        "Beethoven Symphony No. 1 Op. 21",
    )
    candidate = {
        "id": "1",
        "artist": "Osmo Vanska",
        "title": "Beethoven: Symphony No. 1",
        "date": "2020-01-01",
        "tracks": "4",
    }
    service.tidal_service.search_albums.side_effect = lambda query: (
        [candidate] if query == recommendation.work else []
    )

    assert service.search_service.find_best_match(recommendation) is None
    assert service.search_service.candidates[0].id == 1
    queries = [call.args[0] for call in service.tidal_service.search_albums.call_args_list]
    assert recommendation.work in queries
    assert "Beethoven Symphonies Nos 1 6" in queries
    assert len(service.search_service._fallback_queries(recommendation)) <= 3


def test_candidate_context_is_capped_deduplicated_and_reset(service):
    candidates = [
        {
            "id": str(index),
            "artist": "Other Artist",
            "title": f"Other Album {index}",
            "date": "2020-01-01",
            "tracks": "4",
        }
        for index in range(30)
    ]
    service.tidal_service.search_albums.return_value = candidates + candidates

    assert service.search_service.find_best_match(Recommendation("Artist", "Target")) is None
    assert len(service.search_service.candidates) == 20
    assert len({candidate.id for candidate in service.search_service.candidates}) == 20
    service.tidal_service.search_albums.return_value = []
    assert service.search_service.find_best_match(Recommendation("Artist", "Missing")) is None
    assert service.search_service.candidates == []


@pytest.mark.parametrize(
    "title",
    [
        "Beethoven: Complete Symphonies",
        "Beethoven: Symphony No. 1 (Highlights)",
        "Beethoven: Symphony No. 2, Op. 36",
    ],
)
def test_wrong_or_incomplete_symphonies_are_not_candidates(service, title):
    recommendation = Recommendation("Karajan", title, "Beethoven Symphony No. 1 Op. 21")
    service.tidal_service.search_albums.return_value = [
        {"id": "1", "artist": "Karajan", "title": title, "date": "2020-01-01", "tracks": "8"}
    ]

    assert service.search_service.find_best_match(recommendation) is None
    assert service.search_service.candidates == []


@pytest.mark.parametrize(
    "title",
    [
        "Beethoven: Symphony No. 1, Op. 21",
        "Beethoven: Symphony I",
        "Beethoven: Symphony No. 1 / Piano Concerto No. 2",
        "Beethoven: Symphonies Nos. 1 & 2",
        "Beethoven: Symphonies Nos. 1 and 6",
        "Beethoven: Symphony No. 1 & 2",
        "Beethoven: Symphony No. 1 / Symphony No. 2",
        "Beethoven: Symphony No. 1–2",
    ],
)
def test_album_containing_requested_symphony_is_allowed(service, title):
    assert service.search_service.matches_requested_work(
        Recommendation("Artist", "Title", "Beethoven Symphony No. 1 Op. 21"), title
    )


def test_coupled_symphony_is_allowed_without_model_work_field(service):
    title = "Beethoven: Symphonies Nos. 1 & 2"
    assert service.search_service.matches_requested_work(Recommendation("Karajan", title), title)


def test_coupled_first_album_skips_already_covered_second_symphony(service, capsys):
    recommendations = [
        {
            "artist": "Karajan",
            "album": "Beethoven: Symphonies Nos. 1 & 2",
            "work": "Beethoven Symphony No. 1 Op. 21",
        },
        {
            "artist": "Barenboim",
            "album": "Beethoven: Symphony No. 2, Op. 36",
            "work": "Beethoven Symphony No. 2 Op. 36",
        },
    ]
    service.tidal_service.search_albums.return_value = [
        {
            "id": "12",
            "artist": "Karajan",
            "title": recommendations[0]["album"],
            "date": "2020-01-01",
            "tracks": "8",
        },
        {
            "id": "1",
            "artist": "Barenboim",
            "title": "Beethoven: Symphony No. 1, Op. 21",
            "date": "2020-01-01",
            "tracks": "4",
        },
        {
            "id": "2",
            "artist": "Barenboim",
            "title": recommendations[1]["album"],
            "date": "2020-01-01",
            "tracks": "4",
        },
    ]
    service.ai_client.make_request.side_effect = [
        response(recommendations),
        response({"candidate_id": "1"}),
    ]

    mock_symphony_tracks(
        service,
        {
            12: ["Beethoven: Symphony No. 1"] * 4 + ["Beethoven: Symphony No. 2"] * 4,
        },
    )
    assert service.get_prompt_recommendations_and_enqueue("first two symphonies by Beethoven") == 1
    service.tidal_service.add_album_to_queue.assert_called_once_with(12)
    service.ai_client.make_request.assert_called_once()
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "Already covered" in output
    assert "Covered 2 of 2 requested symphonies with 1 album" in output


def test_ai_selection_cannot_repeat_already_covered_works(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.search_service.candidates = [album_result(title="Beethoven: Symphonies Nos. 1 & 2")]
    service.ai_client.make_request.return_value = response({"candidate_id": "1"})

    assert (
        service._resolve_prompt_recommendation(
            Recommendation("Karajan", "Title", "Beethoven Symphony No. 1"),
            "first two symphonies",
            covered={("beethoven", 2)},
        )
        is None
    )
    service.tidal_service.add_album_to_queue.assert_not_called()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Beethoven: Symphonies Nos. 1 & 2", [1, 2]),
        ("Beethoven: Symphonies Nos. 1, 2 and 3", [1, 2, 3]),
        ("Beethoven: Symphonies Nos. 1–4", [1, 2, 3, 4]),
        ("Beethoven: Symphonies I & II", [1, 2]),
        ("Beethoven: Symphony No. 1 / Symphony No. 2", [1, 2]),
        ("Beethoven: Symphony No. 1, Op. 21 / Piano Concerto No. 2", [1]),
    ],
)
def test_numbered_symphony_coverage_parser(service, title, expected):
    assert service.search_service.symphony_numbers(title) == expected


@pytest.mark.parametrize("test_mode", [False, True])
def test_two_coupled_albums_complete_first_four_in_order(service, test_mode, capsys):
    recommendations = [
        Recommendation(
            "Artist", f"Beethoven: Symphony No. {number}", f"Beethoven Symphony No. {number}"
        )
        for number in range(1, 5)
    ]
    service.search_service.find_best_match = Mock(
        side_effect=[
            album_result(12, "Beethoven: Symphonies Nos. 1 & 2"),
            album_result(34, "Beethoven: Symphonies Nos. 3 & 4"),
        ]
    )

    mock_symphony_tracks(
        service,
        {
            12: ["Beethoven: Symphony No. 1"] * 2 + ["Beethoven: Symphony No. 2"] * 2,
            34: ["Beethoven: Symphony No. 3"] * 2 + ["Beethoven: Symphony No. 4"] * 2,
        },
    )
    resolved = service._process_prompt_recommendations(
        recommendations, "first four", test_mode=test_mode
    )

    assert len(resolved) == 2
    searched = [call.args[0].work for call in service.search_service.find_best_match.call_args_list]
    assert searched == ["Beethoven Symphony No. 1", "Beethoven Symphony No. 3"]
    second_call = service.search_service.find_best_match.call_args_list[1]
    # Overlap is removed from actual tracks, not by excluding coupled albums during search.
    assert second_call.kwargs["covered"] == set()
    if test_mode:
        service.tidal_service.add_album_to_queue.assert_not_called()
    else:
        assert [
            call.args[0] for call in service.tidal_service.add_album_to_queue.call_args_list
        ] == [12, 34]
    service.ai_client.make_request.assert_not_called()
    service._display_work_coverage(recommendations, resolved)
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "Covered 4 of 4 requested symphonies with 2 albums" in output


def test_overlapping_later_album_is_excluded_from_candidates(service):
    coupled = "Beethoven: Symphonies Nos. 2 & 3"
    service.tidal_service.search_albums.return_value = [
        {"id": "23", "artist": "Artist", "title": coupled, "date": "2020-01-01", "tracks": "8"}
    ]

    assert (
        service.search_service.find_best_match(
            Recommendation("Artist", coupled, "Beethoven Symphony No. 3"),
            covered={("beethoven", 2)},
        )
        is None
    )
    assert service.search_service.candidates == []


def test_unrequested_symphonies_are_excluded_from_candidates(service):
    title = "Beethoven: Symphonies Nos. 1 & 6"
    service.tidal_service.search_albums.return_value = [
        {"id": "16", "artist": "Artist", "title": title, "date": "2020-01-01", "tracks": "8"}
    ]

    assert (
        service.search_service.find_best_match(
            Recommendation("Artist", title, "Beethoven Symphony No. 1"),
            allowed={("beethoven", number) for number in range(1, 5)},
        )
        is None
    )
    assert service.search_service.candidates == []


def test_failed_enqueue_does_not_mark_symphonies_covered(service):
    recommendations = [
        Recommendation("Artist", "Beethoven: Symphony No. 1", "Beethoven Symphony No. 1"),
        Recommendation("Artist", "Beethoven: Symphony No. 2", "Beethoven Symphony No. 2"),
    ]
    service.search_service.find_best_match = Mock(
        side_effect=[
            album_result(12, "Beethoven: Symphonies Nos. 1 & 2"),
            album_result(2, "Beethoven: Symphony No. 2"),
        ]
    )
    mock_symphony_tracks(
        service,
        {
            12: ["Beethoven: Symphony No. 1"] * 2 + ["Beethoven: Symphony No. 2"] * 2,
        },
    )
    service.tidal_service.add_album_to_queue.side_effect = RuntimeError("Failed")

    resolved = service._process_prompt_recommendations(recommendations, "first two")

    assert resolved == []
    assert service.search_service.find_best_match.call_count == 1
    service.tidal_service.add_album_to_queue.assert_called_once_with(12)


def test_album_with_another_composer_does_not_cover_wrong_symphony(service):
    recommendation = Recommendation("Artist", "Title", "Beethoven Symphony No. 1")
    title = "Beethoven: Symphony No. 1 / Brahms: Symphony No. 2"

    assert service.search_service.coverage_keys(recommendation, title) == {
        ("beethoven", 1),
        ("brahms", 2),
    }
    assert not service.search_service.matches_requested_work(
        Recommendation("Artist", "Title", "Beethoven Symphony No. 2"), title
    )


def test_coverage_is_separate_for_each_composer(service):
    recommendations = [
        Recommendation("Artist", "Beethoven: Symphony No. 1", "Beethoven Symphony No. 1"),
        Recommendation("Artist", "Brahms: Symphony No. 1", "Brahms Symphony No. 1"),
    ]
    service.search_service.find_best_match = Mock(
        side_effect=[
            album_result(1, "Beethoven: Symphony No. 1"),
            album_result(2, "Brahms: Symphony No. 1"),
        ]
    )

    mock_symphony_tracks(
        service,
        {
            1: ["Beethoven: Symphony No. 1"] * 4,
            2: ["Brahms: Symphony No. 1"] * 4,
        },
    )
    assert len(service._process_prompt_recommendations(recommendations, "two composers")) == 2


def test_clarification_prompt_tells_model_already_covered_works(service):
    service.search_service.find_best_match = Mock(
        side_effect=[None, album_result(3, "Beethoven: Symphony No. 3")]
    )
    service.ai_client.make_request.return_value = response(
        {"artist": "Artist", "album": "Beethoven: Symphony No. 3"}
    )

    assert (
        service._resolve_prompt_recommendation(
            Recommendation("Artist", "Wrong Title", "Beethoven Symphony No. 3"),
            "first four",
            covered={("beethoven", 1), ("beethoven", 2)},
        )
        is not None
    )
    prompt = service.ai_client.make_request.call_args.args[0]
    assert "Already covered symphonies" in prompt
    assert '["beethoven", 2]' in prompt


def test_clarification_preserves_work_during_retry(service):
    recommendation = Recommendation("Artist", "Wrong Title", "Beethoven Symphony No. 1")
    service.search_service.find_best_match = Mock(side_effect=[None, album_result()])
    service.ai_client.make_request.return_value = response(
        {"artist": "Artist", "album": "Better Title", "work": "Beethoven Symphony No. 9"}
    )

    assert service._resolve_prompt_recommendation(recommendation, "first four") is not None
    corrected = service.search_service.find_best_match.call_args.args[0]
    assert corrected.work == recommendation.work


def test_prompt_uses_five_only_as_default():
    prompt = PromptTemplates.text_prompt_recommendation("relaxing music")

    assert "Use 5 albums only if no quantity is specified" in prompt
    assert "credited performer, orchestra, or conductor" in prompt
    assert "Preserve any requested order" in prompt


def test_beethoven_first_four_are_queued_in_order_after_clarification(service):
    query = "give me first 4 syphonies by Beethoven"
    recommendations = [
        {"artist": "Beethoven", "album": f"Symphony No. {number}"} for number in range(1, 5)
    ]
    corrected = [
        {"artist": "Berlin Philharmonic", "album": f"Beethoven: Symphony No. {number}"}
        for number in range(1, 5)
    ]
    service.ai_client.make_request.side_effect = [
        response(recommendations),
        *(response(item) for item in corrected),
    ]

    def search_albums(search_query):
        for number, item in enumerate(corrected, start=1):
            if search_query == f"{item['artist']} {item['album']}":
                return [
                    {
                        "id": str(number),
                        "artist": item["artist"],
                        "title": item["album"],
                        "date": "2020-01-01",
                        "tracks": "4",
                    }
                ]
        return []

    service.tidal_service.search_albums.side_effect = search_albums

    assert service.get_prompt_recommendations_and_enqueue(query) == 4
    assert [call.args[0] for call in service.tidal_service.add_album_to_queue.call_args_list] == [
        1,
        2,
        3,
        4,
    ]
    assert service.ai_client.make_request.call_count == 5
    for call in service.ai_client.make_request.call_args_list[1:]:
        assert call.args[1] == ResponseType.CLARIFICATION
        assert query in call.args[0]
        assert "preserve the requested work" in call.args[0]
    explained = service._generate_prompt_explanation.call_args.args[1]
    assert [rec.album for rec in explained] == [item["album"] for item in corrected]


def test_clarification_has_bounded_attempts(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.ai_client.make_request.side_effect = [
        response({"artist": "Artist", "album": "Attempt Two"}),
        response({"artist": "Artist", "album": "Attempt Three"}),
    ]

    assert (
        service._resolve_prompt_recommendation(Recommendation("Artist", "First"), "music") is None
    )
    assert service.search_service.find_best_match.call_count == 3
    assert service.ai_client.make_request.call_count == 2
    last_prompt = service.ai_client.make_request.call_args.args[0]
    assert "First" in last_prompt
    assert "Attempt Two" in last_prompt


def test_clarification_stops_on_normalized_repeat(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.ai_client.make_request.return_value = response({"artist": "ARTIST.", "album": "first!"})

    assert (
        service._resolve_prompt_recommendation(Recommendation("Artist", "First"), "music") is None
    )
    service.search_service.find_best_match.assert_called_once()
    service.ai_client.make_request.assert_called_once()


def test_clarification_stops_on_cycle(service):
    service.search_service.find_best_match = Mock(return_value=None)
    service.ai_client.make_request.side_effect = [
        response({"artist": "Artist", "album": "Second"}),
        response({"artist": "Artist", "album": "First"}),
    ]

    assert (
        service._resolve_prompt_recommendation(Recommendation("Artist", "First"), "music") is None
    )
    assert service.search_service.find_best_match.call_count == 2
    assert service.ai_client.make_request.call_count == 2


@pytest.mark.parametrize(
    "clarification",
    [
        AIResponse(None, False, "API unavailable"),
        AIResponse("not a recommendation", True),
        AIResponse('{"artist":', True),
        response(None),
        response({"artist": "Artist", "album": ""}),
        response([{"artist": "A", "album": "One"}, {"artist": "B", "album": "Two"}]),
    ],
)
def test_unusable_clarification_is_skipped(service, clarification):
    service.search_service.find_best_match = Mock(return_value=None)
    service.ai_client.make_request.return_value = clarification

    assert (
        service._resolve_prompt_recommendation(Recommendation("Artist", "First"), "music") is None
    )
    service.ai_client.make_request.assert_called_once()


def test_prompt_test_mode_clarifies_without_queue_changes(service):
    service.ai_client.make_request.side_effect = [
        response([{"artist": "Wrong Artist", "album": "Wrong Title"}]),
        response({"artist": "Recording Artist", "album": "Correct Title"}),
    ]
    service.search_service.find_best_match = Mock(side_effect=[None, album_result()])

    service.get_prompt_recommendations_test_mode("one album")

    service.tidal_service.add_album_to_queue.assert_not_called()
    assert service.ai_client.make_request.call_count == 2
    service._generate_prompt_explanation.assert_called_once_with(
        "one album", [Recommendation("Recording Artist", "Correct Title")]
    )


def test_search_errors_do_not_trigger_ai_clarification(service):
    service.search_service.find_best_match = Mock(side_effect=SearchError("Player offline"))

    assert (
        service._process_prompt_recommendations([Recommendation("Artist", "Album")], "music") == []
    )
    service.ai_client.make_request.assert_not_called()


def test_queue_errors_do_not_trigger_ai_clarification(service):
    service.search_service.find_best_match = Mock(return_value=album_result())
    service.tidal_service.add_album_to_queue.side_effect = RuntimeError("Player offline")

    assert (
        service._process_prompt_recommendations([Recommendation("Artist", "Album")], "music") == []
    )
    service.ai_client.make_request.assert_not_called()


def test_duplicate_resolved_albums_are_not_queued_twice(service):
    service.search_service.find_best_match = Mock(return_value=album_result())

    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", "First"), Recommendation("Artist", "Second")], "music"
    )

    assert len(resolved) == 1
    service.tidal_service.add_album_to_queue.assert_called_once_with(1)


def test_failed_album_does_not_prevent_later_album_from_being_queued(service):
    service.search_service.find_best_match = Mock(side_effect=[None, album_result()])
    service.ai_client.make_request.return_value = response(None)

    resolved = service._process_prompt_recommendations(
        [Recommendation("Artist", "Unavailable"), Recommendation("Artist", "Available")], "music"
    )

    assert len(resolved) == 1
    service.tidal_service.add_album_to_queue.assert_called_once_with(1)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('[{"artist": " A ", "album": " B (Live) "}]', [Recommendation("A", "B (Live)")]),
        ('```json\n[{"artist": "A", "album": "B"}]\n```', [Recommendation("A", "B")]),
        ('{"recommendations": [{"artist": "A", "album": "B"}]}', [Recommendation("A", "B")]),
        ('[{"artist": null, "album": "B"}, {"artist": "A"}]', []),
        (
            "1. Jay-Jay Johanson - Album (Live)",
            [Recommendation("Jay-Jay Johanson", "Album (Live)")],
        ),
        ('[{"artist":', []),
    ],
)
def test_recommendation_parser_handles_structured_and_legacy_responses(content, expected):
    assert RecommendationParser.parse_recommendations(content) == expected


def test_text_prompt_retries_when_model_rambles_instead_of_answer(service):
    service.ai_client.make_request.side_effect = [
        AIResponse("Let me reason about available recordings...", True),
        response([{"artist": "Recording Artist", "album": "Album"}]),
    ]
    service.search_service.find_best_match = Mock(return_value=album_result())

    assert service.get_prompt_recommendations_and_enqueue("one album") == 1
    assert service.ai_client.make_request.call_count == 2
    assert service.ai_client.make_request.call_args_list[0].args[1] == ResponseType.RECOMMENDATION
    assert service.ai_client.make_request.call_args_list[0].kwargs == {"json_mode": True}


def test_text_prompt_reports_when_ai_returns_no_recommendations(service, capsys):
    service.ai_client.make_request.return_value = AIResponse("just prose, no list", True)

    assert service.get_prompt_recommendations_and_enqueue("music") == 0
    assert service.ai_client.make_request.call_count == 3
    service.tidal_service.add_album_to_queue.assert_not_called()
    output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "did not return usable recommendations" in output


def test_json_mode_falls_back_when_provider_rejects_response_format():
    from blue_cli.ai_service import AIClient

    completion = Mock(choices=[Mock(message=Mock(content='[{"artist":"A","album":"B"}]'))])
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    mock_client = Mock()
    mock_client.chat.completions.create.side_effect = [
        openai.BadRequestError(
            "unsupported", response=httpx.Response(400, request=request), body=None
        ),
        completion,
    ]
    client = AIClient()

    with (
        patch.object(AIClient, "_get_client", return_value=mock_client),
        patch.object(AIClient, "_get_model", return_value="test-model"),
    ):
        result = client.make_request("prompt", ResponseType.RECOMMENDATION, json_mode=True)

    assert result.success
    calls = mock_client.chat.completions.create.call_args_list
    assert len(calls) == 2
    assert calls[0].kwargs["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1].kwargs
