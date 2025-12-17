"""Tests for AIRecommendationService high-level validation."""

from unittest.mock import Mock, patch

import pytest

from blue_cli.ai_service import AIRecommendationService


@pytest.fixture
def ai_service():
    """Provide an AIRecommendationService with mocked dependencies."""
    with patch("blue_cli.ai_service.TidalService"):
        service = AIRecommendationService(host="example.com", port=11000)

    with (
        patch.object(service, "_get_ai_recommendations", return_value=[]),
        patch.object(service, "_process_recommendations_for_queue", return_value=0),
        patch.object(service, "_process_recommendations_for_test", return_value=0),
        patch.object(service, "_generate_explanation"),
        patch.object(service, "display_service", Mock()),
    ):
        yield service


def test_get_recommendations_and_enqueue_requires_metadata(ai_service, capsys):
    """The AI command should not run when artist or album metadata is missing."""
    added = ai_service.get_recommendations_and_enqueue(None, "   ")

    assert added == 0
    ai_service.display_service.display_getting_recommendations.assert_not_called()
    ai_service._get_ai_recommendations.assert_not_called()

    captured = capsys.readouterr()
    assert "Unable to determine the current artist" in captured.out


def test_get_recommendations_test_mode_requires_metadata(ai_service):
    """Test mode should short-circuit when metadata is missing."""
    ai_service.get_recommendations_test_mode("", None)

    ai_service.display_service.display_getting_recommendations.assert_not_called()
    ai_service._get_ai_recommendations.assert_not_called()
