"""Tests for AlbumSearchService improved search functionality."""

from unittest.mock import Mock

import pytest

from blue_cli.ai_service import AlbumSearchService, Recommendation, SearchError, SearchResult


class TestAlbumSearchService:
    """Test the AlbumSearchService class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_tidal_service = Mock()
        self.search_service = AlbumSearchService(self.mock_tidal_service)

        # Sample album data for testing
        self.sample_albums = [
            {
                "id": "305664133",
                "artist": "A. R. Kane",
                "title": "69",
                "date": "1988-01-01",
                "tracks": "10",
            },
            {
                "id": "37267701",
                "artist": "The Magnetic Fields",
                "title": "69 Love Songs",
                "date": "1999-09-07",
                "tracks": "69",
            },
            {
                "id": "108681532",
                "artist": "Wilson Tanner",
                "title": "69",
                "date": "2016-04-01",
                "tracks": "8",
            },
        ]

    def test_find_best_artist_match_exact_match(self):
        """Test exact artist name matching (case insensitive)."""
        albums = self.sample_albums

        # Test exact match (case insensitive)
        result = self.search_service._find_best_artist_match(albums, "a. r. kane")
        assert result is not None
        assert result["artist"] == "A. R. Kane"
        assert result["title"] == "69"

    def test_find_best_artist_match_partial_match(self):
        """Test partial artist name matching."""
        albums = self.sample_albums

        # Test partial match
        result = self.search_service._find_best_artist_match(albums, "Magnetic Fields")
        assert result is not None
        assert result["artist"] == "The Magnetic Fields"
        assert result["title"] == "69 Love Songs"

    def test_find_best_artist_match_normalized_match(self):
        """Test normalized artist name matching (removes periods and spaces)."""
        albums = self.sample_albums

        # Test normalized match (A.R. Kane should match A. R. Kane)
        result = self.search_service._find_best_artist_match(albums, "A.R. Kane")
        assert result is not None
        assert result["artist"] == "A. R. Kane"
        assert result["title"] == "69"

        # Test normalized match (ARKane should match A. R. Kane)
        result = self.search_service._find_best_artist_match(albums, "ARKane")
        assert result is not None
        assert result["artist"] == "A. R. Kane"
        assert result["title"] == "69"

    def test_find_best_artist_match_no_match(self):
        """Test when no artist match is found."""
        albums = self.sample_albums

        result = self.search_service._find_best_artist_match(albums, "Nonexistent Artist")
        assert result is None

    def test_find_best_match_strategy_1_success(self):
        """Test successful search with strategy 1 (Artist Album)."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock successful first search
        self.mock_tidal_service.search_albums.return_value = self.sample_albums

        result = self.search_service.find_best_match(recommendation)

        assert result is not None
        assert result.artist == "A. R. Kane"
        assert result.title == "69"
        assert result.id == 305664133
        assert result.tracks == "10"
        assert result.found is True

        # Verify only one search was made
        self.mock_tidal_service.search_albums.assert_called_once_with("A.R. Kane 69")

    def test_find_best_match_strategy_2_fallback(self):
        """Test fallback to strategy 2 (album name only) when strategy 1 fails."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock first search fails, second succeeds
        self.mock_tidal_service.search_albums.side_effect = [[], self.sample_albums]

        result = self.search_service.find_best_match(recommendation)

        assert result is not None
        assert result.artist == "A. R. Kane"
        assert result.title == "69"

        # Verify both searches were made
        assert self.mock_tidal_service.search_albums.call_count == 2
        calls = self.mock_tidal_service.search_albums.call_args_list
        assert calls[0][0][0] == "A.R. Kane 69"  # First strategy
        assert calls[1][0][0] == "69"  # Second strategy

    def test_find_best_match_strategy_3_artist_variations(self):
        """Test fallback to strategy 3 (artist name variations) when strategies 1 and 2 fail."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock first two searches fail, third succeeds
        self.mock_tidal_service.search_albums.side_effect = [[], [], self.sample_albums]

        result = self.search_service.find_best_match(recommendation)

        assert result is not None
        assert result.artist == "A. R. Kane"
        assert result.title == "69"

        # Verify three searches were made
        assert self.mock_tidal_service.search_albums.call_count == 3
        calls = self.mock_tidal_service.search_albums.call_args_list
        assert calls[0][0][0] == "A.R. Kane 69"  # Strategy 1
        assert calls[1][0][0] == "69"  # Strategy 2
        assert calls[2][0][0] == "AR Kane 69"  # Strategy 3 (first variation)

    def test_find_best_match_all_strategies_fail(self):
        """Test when all search strategies fail to find results."""
        recommendation = Recommendation("Nonexistent Artist", "Unknown Album")

        # Mock all searches return empty results
        self.mock_tidal_service.search_albums.return_value = []

        result = self.search_service.find_best_match(recommendation)

        assert result is None

    def test_find_best_match_fallback_to_first_result(self):
        """Test fallback to first result when artist matching fails."""
        recommendation = Recommendation("Different Artist", "69")

        # Mock search returns albums but no artist match
        self.mock_tidal_service.search_albums.return_value = self.sample_albums

        result = self.search_service.find_best_match(recommendation)

        assert result is not None
        # Should return first album when no artist match found
        assert result.artist == "A. R. Kane"
        assert result.title == "69"
        assert result.id == 305664133

    def test_find_best_match_search_error_handling(self):
        """Test error handling when search fails."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock search raises exception
        self.mock_tidal_service.search_albums.side_effect = Exception("API Error")

        with pytest.raises(SearchError) as exc_info:
            self.search_service.find_best_match(recommendation)

        assert "Error searching for A.R. Kane - 69" in str(exc_info.value)
        assert "API Error" in str(exc_info.value)

    def test_find_best_match_artist_variations_generation(self):
        """Test that artist variations are generated correctly."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock first two searches fail, capture the third search attempts
        search_calls = []

        def mock_search(query):
            search_calls.append(query)
            if len(search_calls) <= 2:
                return []
            # Return results on third call to stop the variation loop
            return self.sample_albums

        self.mock_tidal_service.search_albums.side_effect = mock_search

        result = self.search_service.find_best_match(recommendation)

        assert result is not None
        # Check that the expected variations were tried
        expected_calls = [
            "A.R. Kane 69",  # Strategy 1
            "69",  # Strategy 2
            "AR Kane 69",  # Strategy 3: remove periods
        ]
        assert search_calls == expected_calls

    def test_find_best_match_creates_correct_search_result(self):
        """Test that SearchResult is created with correct data types and values."""
        recommendation = Recommendation("A.R. Kane", "69")

        album_data = {
            "id": "305664133",
            "artist": "A. R. Kane",
            "title": "69",
            "date": "1988-01-01",
            "tracks": "10",
        }

        self.mock_tidal_service.search_albums.return_value = [album_data]

        result = self.search_service.find_best_match(recommendation)

        assert isinstance(result, SearchResult)
        assert result.id == 305664133  # Should be converted to int
        assert result.artist == "A. R. Kane"
        assert result.title == "69"
        assert result.date == "1988-01-01"
        assert result.tracks == "10"
        assert result.found is True

    def test_empty_albums_list_handling(self):
        """Test handling of empty albums list."""
        result = self.search_service._find_best_artist_match([], "Any Artist")
        assert result is None

    def test_find_best_match_basic_strategy_used(self, capsys):
        """Test that basic search strategy is used first."""
        recommendation = Recommendation("A.R. Kane", "69")

        # Mock successful first search
        self.mock_tidal_service.search_albums.return_value = self.sample_albums

        result = self.search_service.find_best_match(recommendation)

        # Verify the tidal service was called with basic query
        self.mock_tidal_service.search_albums.assert_called_once_with("A.R. Kane 69")
        assert result is not None


class TestRecommendation:
    """Test the Recommendation dataclass."""

    def test_recommendation_creation(self):
        """Test creating a Recommendation object."""
        rec = Recommendation("Artist Name", "Album Title")
        assert rec.artist == "Artist Name"
        assert rec.album == "Album Title"

    def test_recommendation_immutable(self):
        """Test that Recommendation is frozen/immutable."""
        rec = Recommendation("Artist", "Album")

        # Should not be able to modify frozen dataclass
        with pytest.raises((AttributeError, TypeError)):
            setattr(rec, "artist", "New Artist")


class TestSearchResult:
    """Test the SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a SearchResult object."""
        result = SearchResult(
            id=123456, artist="Test Artist", title="Test Album", date="2023-01-01", tracks=10
        )

        assert result.id == 123456
        assert result.artist == "Test Artist"
        assert result.title == "Test Album"
        assert result.date == "2023-01-01"
        assert result.tracks == 10
        assert result.found is True  # Default value

    def test_search_result_found_default(self):
        """Test that found defaults to True."""
        result = SearchResult(id=123, artist="Artist", title="Title", date="2023-01-01", tracks=5)
        assert result.found is True

    def test_search_result_found_explicit(self):
        """Test setting found explicitly."""
        result = SearchResult(
            id=123, artist="Artist", title="Title", date="2023-01-01", tracks=5, found=False
        )
        assert result.found is False
