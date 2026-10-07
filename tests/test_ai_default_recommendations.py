"""Offline regression tests for current-song recommendation recovery."""

import json
from unittest.mock import Mock, patch

import pytest

from blue_cli.ai_service import (
    AIRecommendationService,
    AIResponse,
    Recommendation,
    ResponseType,
    SearchError,
    SearchResult,
)


@pytest.fixture
def service():
    with patch("blue_cli.ai_service.TidalService"):
        instance = AIRecommendationService(host="example.com", port=11000)
    instance._get_ai_recommendations = Mock()
    instance.ai_client.make_request = Mock()
    instance._generate_explanation = Mock()
    instance.display_service = Mock()
    return instance


def run_default(service, test_mode):
    if test_mode:
        return service.get_recommendations_test_mode(" Current Artist ", " Current Album ")
    return service.get_recommendations_and_enqueue(" Current Artist ", " Current Album ")


@pytest.mark.parametrize("test_mode", [False, True])
def test_default_command_clarifies_missing_release(service, test_mode):
    original = Recommendation("Artist", "Unavailable Album")
    corrected = Recommendation("Credited Artist", "Actual Release")
    result = SearchResult(42, corrected.artist, corrected.album, "2020-01-01", 4)
    service._get_ai_recommendations.return_value = [original]
    service.search_service.find_best_match = Mock(side_effect=[None, result])
    service.ai_client.make_request.return_value = AIResponse(
        json.dumps({"artist": corrected.artist, "album": corrected.album}), True
    )

    count = run_default(service, test_mode)

    assert count == (None if test_mode else 1)
    prompt, response_type = service.ai_client.make_request.call_args.args
    assert "Current Artist" in prompt
    assert "Current Album" in prompt
    assert "Unavailable Album" in prompt
    assert response_type == ResponseType.CLARIFICATION
    assert service.search_service.find_best_match.call_args.args[0] == corrected
    service._generate_explanation.assert_called_once_with(
        "Current Artist", "Current Album", [corrected]
    )
    if test_mode:
        service.tidal_service.add_album_to_queue.assert_not_called()
        service.display_service.display_test_summary.assert_called_once_with(1, 1)
    else:
        service.tidal_service.add_album_to_queue.assert_called_once_with(42)


@pytest.mark.parametrize("test_mode", [False, True])
def test_default_command_uses_candidates_and_skips_duplicate_releases(service, test_mode):
    candidate = SearchResult(42, "Credited Artist", "Actual Release", "2020-01-01", 4)
    service._get_ai_recommendations.return_value = [
        Recommendation("Artist", "Unavailable Album"),
        Recommendation(candidate.artist, candidate.title),
    ]
    service.search_service.find_best_match = Mock(side_effect=[None, candidate])
    service.search_service.candidates = [candidate]
    service.ai_client.make_request.return_value = AIResponse('{"candidate_id": "42"}', True)

    count = run_default(service, test_mode)

    assert count == (None if test_mode else 1)
    assert "Actual Release" in service.ai_client.make_request.call_args.args[0]
    service._generate_explanation.assert_called_once_with(
        "Current Artist", "Current Album", [Recommendation(candidate.artist, candidate.title)]
    )
    assert service.tidal_service.add_album_to_queue.call_count == (0 if test_mode else 1)


@pytest.mark.parametrize("test_mode", [False, True])
def test_default_command_stops_on_repeated_recommendation(service, test_mode):
    recommendation = Recommendation("Artist", "Unavailable Album")
    service._get_ai_recommendations.return_value = [recommendation]
    service.search_service.find_best_match = Mock(return_value=None)
    service.ai_client.make_request.return_value = AIResponse(
        '{"artist": "Artist", "album": "Unavailable Album"}', True
    )

    count = run_default(service, test_mode)

    assert count == (None if test_mode else 0)
    service.ai_client.make_request.assert_called_once()
    service.search_service.find_best_match.assert_called_once()
    service.tidal_service.add_album_to_queue.assert_not_called()
    service._generate_explanation.assert_not_called()


@pytest.mark.parametrize("test_mode", [False, True])
def test_default_command_continues_after_search_error(service, test_mode):
    result = SearchResult(42, "Artist", "Available Album", "2020-01-01", 4)
    service._get_ai_recommendations.return_value = [
        Recommendation("Artist", "Unavailable Album"),
        Recommendation(result.artist, result.title),
    ]
    service.search_service.find_best_match = Mock(side_effect=[SearchError("offline"), result])

    count = run_default(service, test_mode)

    assert count == (None if test_mode else 1)
    service.ai_client.make_request.assert_not_called()
    service._generate_explanation.assert_called_once_with(
        "Current Artist", "Current Album", [Recommendation(result.artist, result.title)]
    )


def test_default_command_does_not_explain_failed_queue_additions(service):
    service._get_ai_recommendations.return_value = [Recommendation("Artist", "Album")]
    service.search_service.find_best_match = Mock(
        return_value=SearchResult(42, "Artist", "Album", "2020-01-01", 4)
    )
    service.search_service.add_to_queue = Mock(return_value=False)

    assert run_default(service, False) == 0

    service.ai_client.make_request.assert_not_called()
    service._generate_explanation.assert_not_called()
