"""Work-signature matching for catalogue titles with composer prefixes and couplings."""

import json
from unittest.mock import Mock

import pytest

from blue_cli.ai_service import AIResponse, AlbumSearchService, Recommendation
from blue_cli.work_identity import signature_matches, work_query, work_signatures


def signature(text):
    signatures = work_signatures(text)
    assert signatures
    return signatures[0]


@pytest.mark.parametrize(
    ("query", "title", "expected"),
    [
        (
            "Lindberg: Al Largo, Cello Concerto No. 2, Era",
            "Magnus Lindberg: Al largo, Cello Concerto No. 2 & Era",
            True,
        ),
        (
            "Rautavaara: Symphony No. 8 'The Journey'",
            'Rautavaara: Symphony No. 8, "The Journey" / Violin Concerto',
            True,
        ),
        (
            "Rautavaara: Symphony No. 8",
            "Rautavaara, E.: Harp Concerto / Symphony No. 8",
            True,
        ),
        ("Rautavaara: Symphony No. 8", "Bruckner: Symphony No. 8", False),
        (
            "MacMillan: The Confession of Isobel Gowdie, Symphony No. 3 'Silence'",
            "MacMillan: The Confession of Isobel Gowdie & Symphony No. 3",
            True,
        ),
        (
            "Weinberg: Violin Concerto, Symphony No. 4",
            "Weinberg: Violin Concerto, Op. 67 & Sonata for 2 Violins, Op. 69 (Live)",
            True,
        ),
        (
            "Weinberg: Symphony No. 4",
            "Weinberg: Violin Concerto, Op. 67 & Sonata for 2 Violins, Op. 69 (Live)",
            False,
        ),
        ("Thomas Adès: Tevot", "Adès: Tevot & Violin Concerto", True),
        (
            "Saariaho: Graal théâtre",
            "Saariaho: Graal théâtre, Château de l'âme & Amers",
            True,
        ),
        ("Saariaho: Graal théâtre", "Saariaho: L'Amour de loin", False),
        (
            "Aho: Trombone Concerto & Trumpet Concerto",
            "Kalevi Aho: Trombone & Trumpet Concertos",
            True,
        ),
        (
            "Aho: Trombone Concerto",
            "Haydn & Hummel: Trumpet Concertos",
            False,
        ),
        (
            "Rachmaninoff Piano Concerto No. 2 Op. 18",
            "Rachmaninov: Piano Concerto No. 2, Op. 18",
            True,
        ),
        ("Beethoven Symphony No. 1 Op. 21", "Beethoven: Symphony No. 2, Op. 36", False),
        ("Beethoven Symphony No. 1 Op. 21", "Beethoven: Symphony I", True),
        (
            "Beethoven Symphony No. 2",
            "Beethoven: Symphony No. 1 / Brahms: Symphony No. 2",
            False,
        ),
    ],
)
def test_signature_match_is_composer_and_work_specific(query, title, expected):
    assert any(signature_matches(item, title) for item in work_signatures(query)) is expected


def test_work_query_uses_surname_and_number():
    assert work_query(signature("Rautavaara: Symphony No. 8 'The Journey'")) == (
        "Rautavaara Symphony No. 8"
    )
    assert work_query(signature("Jörg Widmann: Violin Concerto")) == "Widmann Violin Concerto"
    assert work_query(signature("Jörg Widmann: Violin Concerto"), reverse=True) == (
        "Violin Concerto Widmann"
    )


def test_composer_credited_release_matches_recommended_performer():
    tidal = Mock()
    tidal.search_albums.return_value = [
        {
            "id": "284453761",
            "artist": "Anssi Karttunen",
            "title": "Magnus Lindberg: Al largo, Cello Concerto No. 2 & Era",
            "date": "2016-03-11",
            "tracks": "5",
        }
    ]
    service = AlbumSearchService(tidal)

    result = service.find_best_match(
        Recommendation("Hannu Lintu", "Lindberg: Al Largo, Cello Concerto No. 2, Era")
    )

    assert result is not None and result.id == 284453761


def test_work_search_recovers_when_title_searches_return_fuzzy_sets():
    tidal = Mock()
    target = {
        "id": "341744470",
        "artist": "Jaakko Kuusisto",
        "title": 'Rautavaara: Symphony No. 8, "The Journey" / Violin Concerto',
        "date": "2004-11-30",
        "tracks": "6",
    }
    tidal.search_albums.side_effect = lambda query: (
        [target] if query == "Rautavaara Symphony No. 8" else []
    )
    service = AlbumSearchService(tidal)

    result = service.find_best_match(
        Recommendation("Osmo Vänskä", "Rautavaara: Symphony No. 8 'The Journey'")
    )

    assert result is not None and result.id == 341744470
    queries = [call.args[0] for call in tidal.search_albums.call_args_list]
    assert "Rautavaara Symphony No. 8" in queries


def test_numbered_set_request_rejects_partial_coupling():
    tidal = Mock()
    tidal.search_albums.return_value = [
        {
            "id": "1",
            "artist": "The Cleveland Orchestra",
            "title": "Walker: Antifonys, Lilacs, Sinfonias Nos 4 & 5",
            "date": "2015-01-01",
            "tracks": "6",
        },
        {
            "id": "2",
            "artist": "Gianandrea Noseda",
            "title": "George Walker: Five Sinfonias",
            "date": "2023-09-08",
            "tracks": "10",
        },
    ]
    service = AlbumSearchService(tidal)

    result = service.find_best_match(
        Recommendation("Gianandrea Noseda", "Walker: Sinfonias Nos. 1-5")
    )

    assert result is not None and result.id == 2


def test_coupled_abstract_works_do_not_trigger_track_identification():
    from blue_cli.ai_service import AIRecommendationService

    service = AIRecommendationService.__new__(AIRecommendationService)
    service.tidal_service = Mock()
    service.ai_client = Mock()
    service.ai_client.make_request.return_value = AIResponse(json.dumps(None), True)
    service.ai_client.config = Mock(max_clarification_attempts=2)
    service.search_service = AlbumSearchService(service.tidal_service)
    service.parser = Mock()
    service.display_service = Mock()
    service.explanation_service = Mock()
    service.tidal_service.search_albums.return_value = [
        {
            "id": "284453761",
            "artist": "Anssi Karttunen",
            "title": "Magnus Lindberg: Al largo, Cello Concerto No. 2 & Era",
            "date": "2016-03-11",
            "tracks": "5",
        }
    ]
    service.tidal_service.get_album_tracks_by_id.return_value = [
        {"id": "Tidal:1", "title": "Al largo"},
        {"id": "Tidal:2", "title": "Cello Concerto No. 2: I. —"},
        {"id": "Tidal:3", "title": "Cello Concerto No. 2: II. —"},
        {"id": "Tidal:4", "title": "Cello Concerto No. 2: III. —"},
        {"id": "Tidal:5", "title": "Era"},
    ]

    resolved = service._process_prompt_recommendations(
        [Recommendation("Hannu Lintu", "Lindberg: Al Largo, Cello Concerto No. 2, Era")],
        "contemporary composers who write concertos",
        test_mode=True,
    )

    assert len(resolved) == 1
    service.ai_client.make_request.assert_not_called()
