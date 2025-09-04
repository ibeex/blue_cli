#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import re
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from textwrap import dedent
from typing import Protocol

import openai

from .config import AI_MODEL, HOST, PORT, get_openai_key
from .console import console
from .tidal_service import TidalService

rprint = console.print


class ResponseType(StrEnum):
    """Types of AI responses."""

    RECOMMENDATION = "recommendation"
    GENERAL_EXPLANATION = "general_explanation"
    SPECIFIC_EXPLANATION = "specific_explanation"


@dataclass(slots=True, frozen=True)
class Recommendation:
    """A music recommendation with artist and album."""

    artist: str
    album: str


@dataclass(slots=True)
class SearchResult:
    """Result from searching for an album on Tidal."""

    id: int
    artist: str
    title: str
    date: str
    tracks: int
    found: bool = True


@dataclass(slots=True)
class AIResponse:
    """Structured response from AI service."""

    content: str | None
    success: bool
    error_message: str | None = None


class AIServiceError(Exception):
    """Base exception for AI service errors."""

    pass


class SearchError(AIServiceError):
    """Exception for search-related errors."""

    pass


@dataclass(slots=True, frozen=True)
class AIServiceConfig:
    """Configuration settings for AI service."""

    max_completion_tokens: int = 8000
    recommendation_count: int = 5
    error_key_message: str = (
        "OpenAI API key not found. Please set OPENAI_API_KEY environment variable "
        "or add to ~/Library/Application Support/io.datasette.llm/keys.json"
    )


@dataclass(frozen=True)
class SearchQuery:
    """Value object for search queries."""

    artist: str
    album: str

    @cached_property
    def basic_query(self) -> str:
        """Get basic search query combining artist and album."""
        return f"{self.artist} {self.album}"

    @cached_property
    def album_only_query(self) -> str:
        """Get album-only search query."""
        return self.album

    def artist_variation_queries(self) -> list[str]:
        """Get artist name variations for search."""
        variations = [
            self.artist.replace(".", ""),  # Remove periods
            self.artist.replace(".", " "),  # Replace periods with spaces
            self.artist.replace(" ", ""),  # Remove spaces
        ]
        return [f"{variant} {self.album}" for variant in variations if variant != self.artist]


class SearchStrategy(Protocol):
    """Protocol for different search strategies."""

    def search(self, search_query: SearchQuery, tidal_service: TidalService) -> list[dict]:
        """Execute search strategy and return albums."""
        ...

    def get_description(self, search_query: SearchQuery) -> str:
        """Get description of what this strategy does."""
        ...


@dataclass(slots=True)
class BasicSearchStrategy:
    """Search using artist and album name together."""

    def search(self, search_query: SearchQuery, tidal_service: TidalService) -> list[dict]:
        return tidal_service.search_albums(search_query.basic_query)

    def get_description(self, search_query: SearchQuery) -> str:
        return f"basic search: '{search_query.basic_query}'"


@dataclass(slots=True)
class AlbumOnlySearchStrategy:
    """Search using album name only."""

    def search(self, search_query: SearchQuery, tidal_service: TidalService) -> list[dict]:
        print(f"No results for basic search, trying album name only: '{search_query.album}'")
        albums = tidal_service.search_albums(search_query.album_only_query)
        print(f"Album-only search results: {len(albums)} albums found")
        return albums

    def get_description(self, search_query: SearchQuery) -> str:
        return f"album-only search: '{search_query.album_only_query}'"


@dataclass(slots=True)
class ArtistVariationSearchStrategy:
    """Search using different artist name variations."""

    def search(self, search_query: SearchQuery, tidal_service: TidalService) -> list[dict]:
        for variant_query in search_query.artist_variation_queries():
            print(f"Trying artist variation: '{variant_query}'")
            albums = tidal_service.search_albums(variant_query)
            if albums:
                return albums
        return []

    def get_description(self, search_query: SearchQuery) -> str:
        return "artist variations search"


@dataclass(slots=True)
class SearchStrategyManager:
    """Manages and executes search strategies in order."""

    strategies: list[SearchStrategy] = field(
        default_factory=lambda: [
            BasicSearchStrategy(),
            AlbumOnlySearchStrategy(),
            ArtistVariationSearchStrategy(),
        ]
    )

    def find_albums(self, search_query: SearchQuery, tidal_service: TidalService) -> list[dict]:
        """Try each strategy until albums are found."""
        for strategy in self.strategies:
            albums = strategy.search(search_query, tidal_service)
            if albums:
                return albums
        return []


@dataclass(slots=True, frozen=True)
class PromptTemplates:
    """Centralized prompt templates for AI requests."""

    @staticmethod
    def recommendation_prompt(artist: str, album: str) -> str:
        """Generate prompt for music recommendations."""
        config = AIServiceConfig()
        return dedent(f"""
            Can you provide a list of {config.recommendation_count} bands that are similar in musical sound/style to {artist}
            (specifically their album '{album}'), or that share band members, producers,
            or other key collaborators with them?

            Exclude any Rap or Hip-Hop artists.

            For each band, please include a notable album or release.
            Format your response as: Band Name - Album Name (one per line).
            Nothing more in response, just the list of bands and albums.
        """).strip()

    @staticmethod
    def general_explanation_prompt(
        current_artist: str, current_album: str, recommendations: list[Recommendation]
    ) -> str:
        """Generate prompt for general explanation of recommendations."""
        rec_list = ", ".join([f"{rec.artist} ({rec.album})" for rec in recommendations])
        return dedent(f"""
            I was listening to '{current_album}' by {current_artist} and got these music recommendations: {rec_list}.

            Provide a brief 2-3 sentence explanation of the overall musical connections and themes that link
            these recommendations to {current_artist}'s '{current_album}'.

            Focus on musical style, era, influences, or collaborative connections.
        """).strip()

    @staticmethod
    def specific_explanation_prompt(
        current_artist: str, current_album: str, rec_artist: str, rec_album: str
    ) -> str:
        """Generate prompt for specific recommendation explanation."""
        return dedent(f"""
            Explain in 1-2 sentences why '{rec_album}' by {rec_artist} was recommended based on
            '{current_album}' by {current_artist}.

            Focus on specific musical connections, shared members, producers, similar sound/style, era,
            or influence relationships.
        """).strip()


class AIClient:
    """Handles all OpenAI API interactions with centralized error handling."""

    def __init__(self, config: AIServiceConfig | None = None):
        self._client: openai.OpenAI | None = None
        self.config = config or AIServiceConfig()

    def _get_client(self) -> openai.OpenAI:
        """Get or create OpenAI client with API key validation."""
        if self._client is None:
            api_key = get_openai_key()
            if not api_key:
                raise AIServiceError(self.config.error_key_message)
            self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def make_request(self, prompt: str, response_type: ResponseType) -> AIResponse:
        """Make AI request with standardized error handling."""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=self.config.max_completion_tokens,
            )

            if response and response.choices and response.choices[0].message.content:
                return AIResponse(content=response.choices[0].message.content.strip(), success=True)
            else:
                return AIResponse(
                    content=None, success=False, error_message="Empty response from OpenAI"
                )

        except Exception as e:
            return AIResponse(
                content=None,
                success=False,
                error_message=f"Error getting {response_type.value}: {str(e)}",
            )


class RecommendationParser:
    """Parses AI recommendations into structured data."""

    @staticmethod
    def parse_recommendations(recommendations: str) -> list[Recommendation]:
        """Parse AI recommendations into list of Recommendation objects."""
        recommendations_list = []
        lines = recommendations.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove numbered list prefix (1. 2. etc.)
            line = re.sub(r"^\d+\.\s*", "", line)

            # Extract band and album using regex
            match = re.match(r"^(.+?)\s*-\s*(.+?)(?:\s*\(.*\))?$", line)
            if match:
                artist = match.group(1).strip()
                album = match.group(2).strip()
                recommendations_list.append(Recommendation(artist=artist, album=album))

        return recommendations_list


class AlbumSearchService:
    """Handles album search operations on Tidal."""

    def __init__(
        self, tidal_service: TidalService, strategy_manager: SearchStrategyManager | None = None
    ):
        self.tidal_service = tidal_service
        self.strategy_manager = strategy_manager or SearchStrategyManager()

    def find_best_match(self, recommendation: Recommendation) -> SearchResult | None:
        """Find the best matching album on Tidal using multiple search strategies."""
        try:
            search_query = SearchQuery(recommendation.artist, recommendation.album)
            albums = self.strategy_manager.find_albums(search_query, self.tidal_service)

            if not albums:
                return None

            best_album = self._select_best_match(albums, recommendation.artist)
            return self._create_search_result(best_album)

        except Exception as e:
            raise SearchError(
                f"Error searching for {recommendation.artist} - {recommendation.album}: {str(e)}"
            ) from e

    def _select_best_match(self, albums: list[dict], target_artist: str) -> dict:
        """Select the best matching album from search results."""
        best_album = self._find_best_artist_match(albums, target_artist)
        return best_album if best_album else albums[0]

    def _create_search_result(self, album: dict) -> SearchResult:
        """Create SearchResult from album data."""
        return SearchResult(
            id=int(album["id"]),
            artist=album["artist"],
            title=album["title"],
            date=album["date"],
            tracks=album["tracks"],
            found=True,
        )

    def _find_best_artist_match(self, albums: list, target_artist: str) -> dict | None:
        """Find the album with the best artist name match using guard clauses."""
        target_lower = target_artist.lower()

        # Guard clause: exact matches (case insensitive)
        for album in albums:
            if album["artist"].lower() == target_lower:
                return album

        # Guard clause: partial matches
        for album in albums:
            album_artist_lower = album["artist"].lower()
            if target_lower in album_artist_lower or album_artist_lower in target_lower:
                return album

        # Guard clause: normalized versions (remove periods, spaces)
        target_normalized = target_lower.replace(".", "").replace(" ", "")
        for album in albums:
            album_normalized = album["artist"].lower().replace(".", "").replace(" ", "")
            if target_normalized == album_normalized:
                return album

        return None

    def add_to_queue(self, search_result: SearchResult) -> bool:
        """Add search result to Tidal queue."""
        try:
            self.tidal_service.add_album_to_queue(search_result.id)
            return True
        except Exception as e:
            raise SearchError(
                f"Error adding {search_result.artist} - {search_result.title} to queue: {str(e)}"
            ) from e


class ExplanationService:
    """Generates AI explanations for recommendations."""

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client

    def get_general_explanation(
        self, current_artist: str, current_album: str, recommendations: list[Recommendation]
    ) -> str | None:
        """Get general explanation for all recommendations."""
        prompt = PromptTemplates.general_explanation_prompt(
            current_artist, current_album, recommendations
        )
        response = self.ai_client.make_request(prompt, ResponseType.GENERAL_EXPLANATION)

        if not response.success:
            rprint(f"[dim red]{response.error_message}[/]")
            return None

        return response.content

    def get_specific_explanation(
        self, current_artist: str, current_album: str, recommendation: Recommendation
    ) -> str | None:
        """Get specific explanation for one recommendation."""
        prompt = PromptTemplates.specific_explanation_prompt(
            current_artist, current_album, recommendation.artist, recommendation.album
        )
        response = self.ai_client.make_request(prompt, ResponseType.SPECIFIC_EXPLANATION)

        if not response.success:
            rprint(
                f"[dim red]Error getting explanation for {recommendation.artist}: {response.error_message}[/]"
            )
            return None

        return response.content


@dataclass(slots=True)
class RecommendationDisplayService:
    """Handles console display formatting for recommendations."""

    @staticmethod
    def display_getting_recommendations(
        current_artist: str, current_album: str, test_mode: bool = False
    ) -> None:
        """Display the initial message about getting recommendations."""
        if test_mode:
            rprint(
                f"[bold yellow]TEST MODE:[/] Getting AI recommendations for: [bold blue]{current_artist}[/] - [bold yellow]{current_album}[/]"
            )
        else:
            rprint(
                f"Getting AI recommendations for: [bold blue]{current_artist}[/] - [bold yellow]{current_album}[/]"
            )

    @staticmethod
    def display_recommendations(recommendations: list[Recommendation]) -> None:
        """Display the list of AI recommendations."""
        rec_text = "\n".join([f"{rec.artist} - {rec.album}" for rec in recommendations])
        rprint(f"\n[bold green]AI Recommendations:[/]\n{rec_text}\n")

    @staticmethod
    def display_test_summary(found_count: int, total_count: int) -> None:
        """Display test mode summary."""
        rprint(
            f"\n[bold blue]Test Summary:[/] Found {found_count} out of {total_count} recommendations on Tidal"
        )
        rprint("[dim]Run without --test to actually add albums to queue[/]")

    @staticmethod
    def display_search_progress(recommendation: Recommendation) -> None:
        """Display search progress for a recommendation."""
        rprint(
            f"Searching for: [cyan]{recommendation.artist}[/] - [yellow]{recommendation.album}[/]"
        )

    @staticmethod
    def display_search_result(search_result: SearchResult) -> None:
        """Display a found search result."""
        rprint(f"Added: [green]{search_result.artist} - {search_result.title}[/]")

    @staticmethod
    def display_search_test_result(search_result: SearchResult) -> None:
        """Display a found search result in test mode."""
        rprint(
            f"  Found: [green]{search_result.artist} - {search_result.title}[/] "
            f"({search_result.date}) - {search_result.tracks} tracks"
        )

    @staticmethod
    def display_no_results() -> None:
        """Display no results found message."""
        rprint("  [red]No results found[/]")

    @staticmethod
    def display_search_error(error: str) -> None:
        """Display search error message."""
        rprint(f"  [red]Error searching: {error}[/]")

    @staticmethod
    def display_final_success(added_count: int) -> None:
        """Display final success message."""
        rprint(f"\n[bold green]Successfully added {added_count} albums to queue![/]")


class AIRecommendationService:
    """Service for getting AI-powered music recommendations based on current song."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.tidal_service = TidalService(host=host, port=port)
        self.ai_client = AIClient()
        self.search_service = AlbumSearchService(self.tidal_service)
        self.explanation_service = ExplanationService(self.ai_client)
        self.parser = RecommendationParser()
        self.display_service = RecommendationDisplayService()

    def _get_ai_recommendations(self, artist: str, album: str) -> list[Recommendation]:
        """Get AI recommendations and parse them into structured data."""
        try:
            prompt = PromptTemplates.recommendation_prompt(artist, album)
            response = self.ai_client.make_request(prompt, ResponseType.RECOMMENDATION)

            if not response.success:
                self._handle_ai_error(response.error_message)
                return []

            return self.parser.parse_recommendations(response.content or "")

        except AIServiceError as e:
            rprint(f"[red]Error getting AI recommendations: {str(e)}[/]")
            return []

    def _handle_ai_error(self, error_message: str | None) -> None:
        """Handle AI service errors with user-friendly messages."""
        rprint(f"[red]Error:[/] {error_message}")
        if error_message and "API key not found" in error_message:
            rprint("Please set your OpenAI API key:")
            rprint("  - Environment: export OPENAI_API_KEY=your_key_here")
            rprint("  - Or add to: ~/Library/Application Support/io.datasette.llm/keys.json")

    def _search_and_add_album(self, recommendation: Recommendation) -> bool:
        """Search for an album and add it to the queue."""
        try:
            self.display_service.display_search_progress(recommendation)

            search_result = self.search_service.find_best_match(recommendation)
            if not search_result:
                rprint(
                    f"[red]No results found for {recommendation.artist} - {recommendation.album}[/]"
                )
                return False

            if not self.search_service.add_to_queue(search_result):
                return False

            self.display_service.display_search_result(search_result)
            return True

        except SearchError as e:
            rprint(f"[red]{str(e)}[/]")
            return False

    def get_recommendations_and_enqueue(self, current_artist: str, current_album: str) -> int:
        """
        Get AI recommendations for the current artist and add albums to queue.

        Args:
            current_artist: The artist name from the currently playing song
            current_album: The album name from the currently playing song

        Returns:
            Number of albums successfully added to queue
        """
        self.display_service.display_getting_recommendations(current_artist, current_album)

        recommendations = self._get_ai_recommendations(current_artist, current_album)
        if not recommendations:
            return 0

        self.display_service.display_recommendations(recommendations)
        added_count = self._process_recommendations_for_queue(recommendations)

        self.display_service.display_final_success(added_count)

        if recommendations:
            self._generate_explanation(current_artist, current_album, recommendations)

        return added_count

    def get_recommendations_test_mode(self, current_artist: str, current_album: str) -> None:
        """
        Get AI recommendations and display search results without adding to queue.

        Args:
            current_artist: The artist name from the currently playing song
            current_album: The album name from the currently playing song
        """
        self.display_service.display_getting_recommendations(
            current_artist, current_album, test_mode=True
        )

        recommendations = self._get_ai_recommendations(current_artist, current_album)
        if not recommendations:
            return

        self.display_service.display_recommendations(recommendations)
        found_count = self._process_recommendations_for_test(recommendations)

        self.display_service.display_test_summary(found_count, len(recommendations))

        if recommendations:
            self._generate_explanation(current_artist, current_album, recommendations)

    def _process_recommendations_for_queue(self, recommendations: list[Recommendation]) -> int:
        """Process recommendations by adding them to queue."""
        added_count = 0
        for recommendation in recommendations:
            if self._search_and_add_album(recommendation):
                added_count += 1
        return added_count

    def _process_recommendations_for_test(self, recommendations: list[Recommendation]) -> int:
        """Process recommendations in test mode (search only, no queue addition)."""
        found_count = 0
        for recommendation in recommendations:
            try:
                self.display_service.display_search_progress(recommendation)

                search_result = self.search_service.find_best_match(recommendation)
                if search_result:
                    self.display_service.display_search_test_result(search_result)
                    found_count += 1
                else:
                    self.display_service.display_no_results()

            except SearchError as e:
                self.display_service.display_search_error(str(e))

        return found_count

    def _generate_explanation(
        self,
        current_artist: str,
        current_album: str,
        recommendations: list[Recommendation],
    ) -> None:
        """Generate AI explanation for the recommendations."""
        rprint("\n[bold magenta]🤖 AI Explanation[/]")

        # Get general explanation
        general_explanation = self.explanation_service.get_general_explanation(
            current_artist, current_album, recommendations
        )
        if general_explanation:
            rprint(f"\n[bold cyan]Why these recommendations?[/]\n{general_explanation}")

        # Get specific explanations for each recommendation
        rprint("\n[bold cyan]Individual explanations:[/]")
        for i, recommendation in enumerate(recommendations, 1):
            specific_explanation = self.explanation_service.get_specific_explanation(
                current_artist, current_album, recommendation
            )
            if specific_explanation:
                rprint(f"\n[yellow]{i}. {recommendation.artist} - {recommendation.album}[/]")
                rprint(f"   {specific_explanation}")
