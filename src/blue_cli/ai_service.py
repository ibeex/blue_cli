#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import re
from dataclasses import dataclass
from enum import StrEnum
from textwrap import dedent

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
class PromptTemplates:
    """Centralized prompt templates for AI requests."""

    @staticmethod
    def recommendation_prompt(artist: str, album: str) -> str:
        """Generate prompt for music recommendations."""
        return dedent(f"""
            Can you provide a list of 5 bands that are similar in musical sound/style to {artist}
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

    def __init__(self):
        self._client: openai.OpenAI | None = None

    def _get_client(self) -> openai.OpenAI:
        """Get or create OpenAI client with API key validation."""
        if self._client is None:
            api_key = get_openai_key()
            if not api_key:
                raise AIServiceError(
                    "OpenAI API key not found. Please set OPENAI_API_KEY environment variable "
                    "or add to ~/Library/Application Support/io.datasette.llm/keys.json"
                )
            self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def make_request(self, prompt: str, response_type: ResponseType) -> AIResponse:
        """Make AI request with standardized error handling."""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=8000,
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

    def __init__(self, tidal_service: TidalService):
        self.tidal_service = tidal_service

    def find_best_match(self, recommendation: Recommendation) -> SearchResult | None:
        """Find the best matching album on Tidal using multiple search strategies."""
        try:
            # Strategy 1: Search for "Artist Album"
            search_query = f"{recommendation.artist} {recommendation.album}"
            albums = self.tidal_service.search_albums(search_query)

            # Strategy 2: If no results, try searching just the album name
            if not albums:
                print(
                    f"No results for '{search_query}', trying album name only: '{recommendation.album}'"
                )
                albums = self.tidal_service.search_albums(recommendation.album)
                print(f"Album-only search results: {len(albums)} albums found")

            # Strategy 3: If still no results, try artist name variations
            if not albums:
                # Try different artist name formats
                artist_variations = [
                    recommendation.artist.replace(".", ""),  # Remove periods
                    recommendation.artist.replace(".", " "),  # Replace periods with spaces
                    recommendation.artist.replace(" ", ""),  # Remove spaces
                ]

                for artist_variant in artist_variations:
                    if artist_variant != recommendation.artist:
                        variant_query = f"{artist_variant} {recommendation.album}"
                        print(f"Trying artist variation: '{variant_query}'")
                        albums = self.tidal_service.search_albums(variant_query)
                        if albums:
                            break

            if not albums:
                return None

            # Find best match (prefer exact artist match)
            best_album = self._find_best_artist_match(albums, recommendation.artist)

            if not best_album:
                best_album = albums[0]  # Fallback to first result

            return SearchResult(
                id=int(best_album["id"]),
                artist=best_album["artist"],
                title=best_album["title"],
                date=best_album["date"],
                tracks=best_album["tracks"],
                found=True,
            )

        except Exception as e:
            raise SearchError(
                f"Error searching for {recommendation.artist} - {recommendation.album}: {str(e)}"
            ) from e

    def _find_best_artist_match(self, albums: list, target_artist: str) -> dict | None:
        """Find the album with the best artist name match."""
        target_lower = target_artist.lower()

        # First pass: look for exact matches (case insensitive)
        for album in albums:
            if album["artist"].lower() == target_lower:
                return album

        # Second pass: look for partial matches
        for album in albums:
            album_artist_lower = album["artist"].lower()
            if target_lower in album_artist_lower or album_artist_lower in target_lower:
                return album

        # Third pass: try normalized versions (remove periods, spaces)
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

    def _get_ai_recommendations(self, artist: str, album: str) -> list[Recommendation]:
        """Get AI recommendations and parse them into structured data."""
        try:
            prompt = PromptTemplates.recommendation_prompt(artist, album)
            response = self.ai_client.make_request(prompt, ResponseType.RECOMMENDATION)

            if not response.success:
                rprint(f"[red]Error:[/] {response.error_message}")
                if "API key not found" in str(response.error_message):
                    rprint("Please set your OpenAI API key:")
                    rprint("  - Environment: export OPENAI_API_KEY=your_key_here")
                    rprint(
                        "  - Or add to: ~/Library/Application Support/io.datasette.llm/keys.json"
                    )
                return []

            return self.parser.parse_recommendations(response.content or "")

        except AIServiceError as e:
            rprint(f"[red]Error getting AI recommendations: {str(e)}[/]")
            return []

    def _search_and_add_album(self, recommendation: Recommendation) -> bool:
        """Search for an album and add it to the queue."""
        try:
            rprint(
                f"Searching for: [cyan]{recommendation.artist}[/] - [yellow]{recommendation.album}[/]"
            )

            search_result = self.search_service.find_best_match(recommendation)
            if not search_result:
                rprint(
                    f"[red]No results found for {recommendation.artist} - {recommendation.album}[/]"
                )
                return False

            success = self.search_service.add_to_queue(search_result)
            if success:
                rprint(f"Added: [green]{search_result.artist} - {search_result.title}[/]")
            return success

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
        rprint(
            f"Getting AI recommendations for: [bold blue]{current_artist}[/] - [bold yellow]{current_album}[/]"
        )

        # Get AI recommendations
        recommendations = self._get_ai_recommendations(current_artist, current_album)
        if not recommendations:
            return 0

        # Display recommendations
        rec_text = "\n".join([f"{rec.artist} - {rec.album}" for rec in recommendations])
        rprint(f"\n[bold green]AI Recommendations:[/]\n{rec_text}\n")

        # Process recommendations
        added_count = 0
        for recommendation in recommendations:
            if self._search_and_add_album(recommendation):
                added_count += 1

        rprint(f"\n[bold green]Successfully added {added_count} albums to queue![/]")

        # Generate explanation for the recommendations
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
        rprint(
            f"[bold yellow]TEST MODE:[/] Getting AI recommendations for: [bold blue]{current_artist}[/] - [bold yellow]{current_album}[/]"
        )

        # Get AI recommendations
        recommendations = self._get_ai_recommendations(current_artist, current_album)
        if not recommendations:
            return

        # Display recommendations
        rec_text = "\n".join([f"{rec.artist} - {rec.album}" for rec in recommendations])
        rprint(f"\n[bold green]AI Recommendations:[/]\n{rec_text}\n")

        # Test search for each recommendation
        found_count = 0
        for recommendation in recommendations:
            try:
                rprint(
                    f"Searching for: [cyan]{recommendation.artist}[/] - [yellow]{recommendation.album}[/]"
                )

                search_result = self.search_service.find_best_match(recommendation)
                if search_result:
                    rprint(
                        f"  Found: [green]{search_result.artist} - {search_result.title}[/] "
                        f"({search_result.date}) - {search_result.tracks} tracks"
                    )
                    found_count += 1
                else:
                    rprint("  [red]No results found[/]")

            except SearchError as e:
                rprint(f"  [red]Error searching: {str(e)}[/]")

        rprint(
            f"\n[bold blue]Test Summary:[/] Found {found_count} out of {len(recommendations)} recommendations on Tidal"
        )
        rprint("[dim]Run without --test to actually add albums to queue[/]")

        # Generate explanation for the recommendations
        if recommendations:
            self._generate_explanation(current_artist, current_album, recommendations)

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
