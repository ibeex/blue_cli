#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import re

import openai

from .config import HOST, PORT, get_openai_key
from .console import console
from .tidal_service import TidalService

rprint = console.print


class AIRecommendationService:
    """Service for getting AI-powered music recommendations based on current song."""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.tidal_service = TidalService(host=host, port=port)

    def _get_ai_recommendations(self, artist: str, album: str) -> str | None:
        """Get AI recommendations for similar artists and albums."""
        api_key = get_openai_key()
        if not api_key:
            rprint("[red]Error:[/] OpenAI API key not found")
            rprint("Please set your OpenAI API key:")
            rprint("  - Environment: export OPENAI_API_KEY=your_key_here")
            rprint("  - Or add to: ~/Library/Application Support/io.datasette.llm/keys.json")
            return None

        client = openai.OpenAI(api_key=api_key)

        prompt = (
            f"Can you provide a list of 5 bands that are similar in musical style to {artist} "
            f"(specifically their album '{album}'), or that share band members, producers, "
            f"or other key collaborators with them? "
            f"Exclude any Rap or Hip-Hop artists. "
            f"For each band, please include a notable album or release. "
            f"Format your response as: Band Name - Album Name (one per line). "
            f"Nothing more in response, just the list of bands and albums."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=5000,
            )

            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            else:
                rprint("[red]Error: Empty response from OpenAI[/]")
                return None

        except Exception as e:
            rprint(f"[red]Error getting AI recommendations: {str(e)}[/]")
            return None

    def _parse_recommendations(self, recommendations: str) -> list[tuple[str, str]]:
        """Parse AI recommendations into band-album pairs."""
        pairs = []
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
                band_name = match.group(1).strip()
                album_name = match.group(2).strip()
                pairs.append((band_name, album_name))

        return pairs

    def _search_and_add_album(self, band_name: str, album_name: str) -> bool:
        """Search for an album and add it to the queue."""
        try:
            rprint(f"Searching for: [cyan]{band_name}[/] - [yellow]{album_name}[/]")

            # Search for the album on Tidal
            albums = self.tidal_service.search_albums(f"{band_name} {album_name}")

            if not albums:
                rprint(f"[red]No results found for {band_name} - {album_name}[/]")
                return False

            # Find best match (prefer exact artist match)
            best_album = None
            for album in albums:
                if (
                    band_name.lower() in album["artist"].lower()
                    or album["artist"].lower() in band_name.lower()
                ):
                    best_album = album
                    break

            if not best_album:
                best_album = albums[0]  # Fallback to first result

            # Add to queue
            self.tidal_service.add_album_to_queue(best_album["id"])
            rprint(f"Added: [green]{best_album['artist']} - {best_album['title']}[/]")
            return True

        except Exception as e:
            rprint(f"[red]Error searching for {band_name} - {album_name}: {str(e)}[/]")
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

        rprint(f"\n[bold green]AI Recommendations:[/]\n{recommendations}\n")

        # Parse and process recommendations
        band_album_pairs = self._parse_recommendations(recommendations)
        added_count = 0

        for band_name, album_name in band_album_pairs:
            if self._search_and_add_album(band_name, album_name):
                added_count += 1

        rprint(f"\n[bold green]Successfully added {added_count} albums to queue![/]")

        # Generate explanation for the recommendations
        if band_album_pairs:
            self._generate_explanation(current_artist, current_album, band_album_pairs)

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

        rprint(f"\n[bold green]AI Recommendations:[/]\n{recommendations}\n")

        # Parse and test search for each recommendation
        band_album_pairs = self._parse_recommendations(recommendations)
        found_count = 0

        for band_name, album_name in band_album_pairs:
            try:
                rprint(f"Searching for: [cyan]{band_name}[/] - [yellow]{album_name}[/]")

                # Search for the album on Tidal (but don't add to queue)
                albums = self.tidal_service.search_albums(f"{band_name} {album_name}")

                if albums:
                    # Find best match (prefer exact artist match)
                    best_album = None
                    for album in albums:
                        if (
                            band_name.lower() in album["artist"].lower()
                            or album["artist"].lower() in band_name.lower()
                        ):
                            best_album = album
                            break

                    if not best_album:
                        best_album = albums[0]  # Fallback to first result

                    rprint(
                        f"  Found: [green]{best_album['artist']} - {best_album['title']}[/] ({best_album['date']}) - {best_album['tracks']} tracks"
                    )
                    found_count += 1
                else:
                    rprint("  [red]No results found[/]")

            except Exception as e:
                rprint(f"  [red]Error searching: {str(e)}[/]")

        rprint(
            f"\n[bold blue]Test Summary:[/] Found {found_count} out of {len(band_album_pairs)} recommendations on Tidal"
        )
        rprint("[dim]Run without --test to actually add albums to queue[/]")

        # Generate explanation for the recommendations
        if band_album_pairs:
            self._generate_explanation(current_artist, current_album, band_album_pairs)

    def _generate_explanation(
        self,
        current_artist: str,
        current_album: str,
        recommendations: list[tuple[str, str]],
    ) -> None:
        """Generate AI explanation for the recommendations."""
        rprint("\n[bold magenta]🤖 AI Explanation[/]")

        # Get general explanation
        general_explanation = self._get_general_explanation(
            current_artist, current_album, recommendations
        )
        if general_explanation:
            rprint(f"\n[bold cyan]Why these recommendations?[/]\n{general_explanation}")

        # Get specific explanations for each recommendation
        rprint("\n[bold cyan]Individual explanations:[/]")
        for i, (band_name, album_name) in enumerate(recommendations, 1):
            specific_explanation = self._get_specific_explanation(
                current_artist, current_album, band_name, album_name
            )
            if specific_explanation:
                rprint(f"\n[yellow]{i}. {band_name} - {album_name}[/]")
                rprint(f"   {specific_explanation}")

    def _get_general_explanation(
        self,
        current_artist: str,
        current_album: str,
        recommendations: list[tuple[str, str]],
    ) -> str | None:
        """Get general explanation for all recommendations."""
        api_key = get_openai_key()
        if not api_key:
            return None

        client = openai.OpenAI(api_key=api_key)

        # Create list of recommended artists for the prompt
        rec_list = ", ".join([f"{band} ({album})" for band, album in recommendations])

        prompt = (
            f"I was listening to '{current_album}' by {current_artist} and got these music recommendations: {rec_list}. "
            f"Provide a brief 2-3 sentence explanation of the overall musical connections and themes that link "
            f"these recommendations to {current_artist}'s '{current_album}'. Focus on musical style, era, influences, "
            f"or collaborative connections."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=5000,
            )

            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
        except Exception as e:
            rprint(f"[dim red]Error getting general explanation: {str(e)}[/]")

        return None

    def _get_specific_explanation(
        self, current_artist: str, current_album: str, rec_artist: str, rec_album: str
    ) -> str | None:
        """Get specific explanation for one recommendation."""
        api_key = get_openai_key()
        if not api_key:
            return None

        client = openai.OpenAI(api_key=api_key)

        prompt = (
            f"Explain in 1-2 sentences why '{rec_album}' by {rec_artist} was recommended based on "
            f"'{current_album}' by {current_artist}. Focus on specific musical connections, shared members, "
            f"producers, similar sound, era, or influence relationships."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-5-2025-08-07",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=6000,
            )

            if response and response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
        except Exception as e:
            rprint(f"[dim red]Error getting explanation for {rec_artist}: {str(e)}[/]")

        return None
