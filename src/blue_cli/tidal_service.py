import json
import pickle
import random
import re
import urllib.parse
from typing import Any

import html2text
import jmespath
from diskcache import Cache
from pyfzf.pyfzf import FzfPrompt
from rich import print as rprint

from .base_client import BluesoundBaseClient
from .config import cache_path
from .console import console

cache = Cache(cache_path, disk_pickle_protocol=pickle.HIGHEST_PROTOCOL)

h = html2text.HTML2Text()
h.ignore_links = True
h.ignore_images = True

__version__ = "1.0.0"
__author__ = "IbeeX"

ALBUM_VARIANT_PATTERNS = [
    "deluxe",
    "remix",
    "acoustic",
    "expanded",
    "bonus",
    "demo",
]


def _is_album_variant(title: str) -> bool:
    """Check if album title indicates a variant (deluxe, remix, etc.)"""
    title_lower = title.lower()
    matches = re.findall(r"\((.*?)\)", title_lower)
    for content in matches:
        if any(pattern in content for pattern in ALBUM_VARIANT_PATTERNS):
            return True
    return False


def _get_base_album_name(title: str) -> str:
    """Extract base album name without variant info in parentheses"""
    if "(" in title:
        return title[: title.find("(")].strip()
    return title


def _find_standard_version(base_name: str, albums: list):
    """Find a non-variant album matching the base name"""
    for album in albums:
        if not _is_album_variant(album["title"]):
            if _get_base_album_name(album["title"]) == base_name:
                return album
    return None


def _select_best_album(albums: list, prefer_latest: bool = True):
    """
    Select best album, preferring non-variants or standard versions.
    If a variant is selected, tries to find the standard version first.
    Returns (selected_album, list_of_skipped_albums)
    """
    if not albums:
        return None, []

    skipped = []
    remaining = albums.copy()

    while remaining:
        if prefer_latest:
            candidate = sorted(remaining, key=lambda x: x["date"], reverse=True)[0]
        else:
            candidate = random.choice(remaining)

        remaining = [a for a in remaining if a["id"] != candidate["id"]]

        if not _is_album_variant(candidate["title"]):
            return candidate, skipped

        base_name = _get_base_album_name(candidate["title"])
        standard = _find_standard_version(base_name, albums)

        if standard and standard["id"] != candidate["id"]:
            return standard, skipped
        else:
            skipped.append(candidate)

    return None, skipped


class TidalService(BluesoundBaseClient):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(host, port)

    @cache.memoize(expire=60 * 60 * 24)
    def search_artists(self, artist: str = "") -> list[Any]:
        if artist:
            artist_name_url_encoded = urllib.parse.quote(f'"{artist}"')
            url = f"Artists?service=Tidal&expr={artist_name_url_encoded}"
        else:
            url = "Artists?service=Tidal&category=FAVOURITES&sort=recent"

        artists = []

        while url:
            r = self._make_request(url)
            obj = self._parse_xml(r)

            if "error" in obj or "artists" not in obj or "art" not in obj["artists"]:
                return artists

            search_insert = "[]" if isinstance(obj["artists"]["art"], list) else ""
            search_string = f'artists.art{search_insert}.{{ "id": artistid, "name": "#text" }}'

            _artists = jmespath.search(search_string, obj)
            artists.extend(_artists if isinstance(_artists, list) else [_artists])

            url = (
                jmespath.search("artists.nextlink", obj)
                if jmespath.search("artists.nextlink", obj)
                else None
            )

        if not artists:
            return artists

        cache_file = cache_path / "artists.json"
        try:
            with open(cache_file) as f:
                artists_cache = json.load(f)

            # Use list comprehension for lookup
            new_artists = [x for x in artists if x not in artists_cache]
            if new_artists:
                artists_cache.extend(new_artists)
                with open(cache_file, "w") as f:
                    json.dump(artists_cache, f)

        except FileNotFoundError:
            with open(cache_file, "w") as f:
                json.dump(artists, f)

        return artists

    def get_artistid(self, artist: str) -> str:
        artists = json.load(open(cache_path / "artists.json"))
        artist_id = [x["id"] for x in artists if x["name"] == artist][0]
        return artist_id

    @cache.memoize(expire=60 * 60 * 24)
    def get_albums(self, artist_id=""):
        url = f"Albums?service=Tidal&artistid={artist_id}"
        albums = []

        while url:
            r = self._make_request(url)
            obj = self._parse_xml(r)
            if "error" in obj or "album" not in obj["albums"]:
                return albums

            search_insert = "[]" if isinstance(obj["albums"]["album"], list) else ""
            search_string = f'albums.album{search_insert}.{{ "id": albumid, "title": title, "artistid": artistid, "tracks": tracks, "quality": quality, "artist": art, "date": date }}'

            _albums = jmespath.search(search_string, obj)
            albums.extend(_albums if isinstance(_albums, list) else [_albums])

            url = (
                jmespath.search("albums.nextlink", obj)
                if jmespath.search("albums.nextlink", obj)
                else None
            )

        if not albums:
            rprint("No albums found.")
            exit(1)

        return albums

    @cache.memoize(expire=60 * 60 * 24 * 30)
    def get_artis_info(self, artist_id=""):
        url = f"Info?service=Tidal&artistid={artist_id}"
        r = self._make_request(url)
        text = h.handle(r.text)
        # show first 20 linse of the artist info
        if len(text.split("\n")) > 20:
            info = text.split("\n")[:20]
            return "\n".join(info) + "\n...\n"
        return text

    def print_albums(self, albums):
        if not albums:
            console.print("No albums found.")
            return
        for album in albums:
            console.print(
                f"[bold blue]{album['title']}[/bold blue] {album['date']} [bold yellow]Tracks:[/bold yellow] {album['tracks']} [bold cyan]Quality:[/bold cyan] {album['quality']}"
            )

    # @cache.memoize(expire=60 * 60 * 24 * 7)
    def search_albums(self, album: str):
        album_name_url_encoded = urllib.parse.quote(f'"{album}"')
        url = f"Albums?service=Tidal&expr={album_name_url_encoded}"
        albums = []

        while url:
            r = self._make_request(url)
            obj = self._parse_xml(r)
            if "error" in obj or "albums" not in obj or "album" not in obj["albums"]:
                return albums

            search_insert = "[]" if isinstance(obj["albums"]["album"], list) else ""

            search_string = f'albums.album{search_insert}.{{ "id": albumid, "title": title, "tracks": tracks, "quality": quality, "date": date, "artist": art}}'
            _albums = jmespath.search(search_string, obj)
            albums.extend(_albums if isinstance(_albums, list) else [_albums])
            url = (
                jmespath.search("albums.nextlink", obj)
                if jmespath.search("albums.nextlink", obj)
                else None
            )

        if not albums:
            rprint("No albums found.")
            exit(1)
        json.dump(albums, open(cache_path / "albums.json", "w"))
        return albums

    @cache.memoize(expire=60 * 60 * 24 * 7)
    def search_songs(self, song: str):
        song_name_url_encoded = urllib.parse.quote(f'"{song}"')
        url = f"Songs?service=Tidal&expr={song_name_url_encoded}"
        songs = []

        while url:
            r = self._make_request(url)
            obj = self._parse_xml(r)

            if "error" in obj or "songs" not in obj or "song" not in obj["songs"]:
                return songs

            search_insert = "[]" if isinstance(obj["songs"]["song"], list) else ""

            search_string = f'songs.song{search_insert}.{{ "id": songid, "title": title, "artist": art, "quality": quality, "time": time, "artistid": artistid}}'
            _songs = jmespath.search(search_string, obj)
            songs.extend(_songs if isinstance(_songs, list) else [_songs])
            url = (
                jmespath.search("songs.nextlink", obj)
                if jmespath.search("songs.nextlink", obj)
                else None
            )

        if not songs:
            rprint("No song found.")
            exit(1)
        json.dump(songs, open(cache_path / "songs.json", "w"))
        return songs

    def select_album(self, albums):
        SEPARATOR = chr(31)
        artist_albums = [
            f"{x['artist']}{SEPARATOR}: {x['title']} {SEPARATOR}/ {x['date']} - {x['tracks']} - {x['quality']}"
            for x in albums
        ]
        fzf = FzfPrompt("fzf --tmux 90%,80% --preview 'b pr tracks {}'")
        try:
            selected_album = fzf.prompt(artist_albums)[0]
        except IndexError:
            rprint("No album found or selected.")
            exit(1)

        artist, rest = selected_album.split(f"{SEPARATOR}: ", maxsplit=1)
        title, metadata = rest.split(f" {SEPARATOR}/ ", maxsplit=1)
        quality = metadata.split(" - ")[2].strip()
        album_id = next(
            (
                album["id"]
                for album in albums
                if album["artist"] == artist
                and album["title"] == title
                and album["quality"] == quality
            ),
            None,
        )

        if not album_id:
            rprint("Could not find matching album.")
            exit(1)

        return album_id, selected_album

    def select_song(self, songs):
        SEPARATOR = chr(31)
        formatted_songs = [
            f"{song['artist']}{SEPARATOR}: {song['title']} {SEPARATOR}/ {int(song['time']) // 60}:{int(song['time']) % 60:02d} - {song['quality']}"
            for song in songs
        ]
        fzf = FzfPrompt("fzf --tmux 90%,80%")
        try:
            selected_song = fzf.prompt(formatted_songs)[0]
        except IndexError:
            rprint("No song found or selected.")
            exit(1)

        artist, rest = selected_song.split(f"{SEPARATOR}: ", maxsplit=1)
        title, metadata = rest.split(f" {SEPARATOR}/ ", maxsplit=1)
        quality = metadata.split(" - ")[1].strip()
        song_id = next(
            (
                song["id"]
                for song in songs
                if song["artist"] == artist
                and song["title"] == title
                and song["quality"] == quality
            ),
            None,
        )

        if not song_id:
            rprint("Could not find matching song.")
            exit(1)

        return song_id, selected_song

    def parse_album_string(self, album: str) -> tuple[str, str, str, str | None, str]:
        SEPARATOR = chr(31)  # ␟ character

        if SEPARATOR not in album:
            raise ValueError("String does not contain the expected separator.")

        artist, rest = album.split(f"{SEPARATOR}: ", 1)
        album_name, metadata = rest.rsplit(f" {SEPARATOR}/ ", 1)

        if metadata.count(" - ") != 2:
            raise ValueError('String does not contain the expected number of " - " delimiters.')

        album_date, album_tracks, album_quality = metadata.split(" - ")

        return album_name, album_date, album_tracks, album_quality, artist

    def print_tracks(self, tracks):
        console.print(f"[bold green]Artist:[/bold green] {tracks[0]['artist']}")
        console.print(f"[bold blue]Album:[/bold blue] {tracks[0]['album']} {tracks[0]['date']}")

        for track in tracks:
            minutes, seconds = divmod(int(track["duration"]), 60)
            duration = f"{minutes}:{seconds:02d}"
            console.print(
                f" [bold cyan]{track['track']}[/bold cyan] {track['title']} [bold red]{duration}[/bold red] [bold yellow]{track['quality']}[/bold yellow]"
            )

    def get_album_tracks(self, album: str):
        album_name, album_date, album_tracks, album_quality, artist = self.parse_album_string(album)

        albums = json.load(open(cache_path / "albums.json"))
        criteria = {
            "title": album_name,
            "date": album_date,
            "tracks": album_tracks,
            "quality": album_quality,
        }
        if artist:
            criteria["artist"] = artist

        album_id = [
            x["id"] for x in albums if all(x[key] == value for key, value in criteria.items())
        ][0]
        return self.get_album_tracks_by_id(album_id)

    @cache.memoize(expire=60 * 60 * 24 * 30)
    def get_album_tracks_by_id(self, album_id: int):
        url = f"Songs?service=Tidal&albumid={album_id}"
        r = self._make_request(url)
        obj = self._parse_xml(r)
        tracks = jmespath.search(
            'songs.album.song[].{ "track": track, "title": title, "artist": art, "album": alb, "quality": quality, "duration": time, "date": date }',
            obj,
        )

        return tracks

    def add_album_to_queue(self, album_id: int):
        url = f"Add?service=Tidal&albumid={album_id}&playnow=-1&where=last"
        self._make_request(url)

    def add_song_to_queue(self, song_id: int):
        url = f"Add?service=Tidal&songid={song_id}&playnow=-1&where=last"
        self._make_request(url)

    def select_albums_by_artists(self, artists: list[Any]):
        fzf = FzfPrompt("fzf --tmux 90%,80% --preview 'b pr album {}'")
        try:
            artist = fzf.prompt([x["name"] for x in artists])[0]
        except IndexError:
            rprint("No artist found or selected.")
            exit(1)
        artist_id = [x["id"] for x in artists if x["name"] == artist][0]
        albums = self.get_albums(artist_id)
        json.dump(albums, open(cache_path / "albums.json", "w"))
        return albums

    def cli_search_albums(self, album: str):
        if not album:
            album = console.input("Album: ")
        _albums = self.search_albums(album)
        album_id, selected_album = self.select_album(_albums)
        self.add_album_to_queue(album_id)
        rprint(f"Added {selected_album} to queue.")

    def cli_search_songs(self, song: str):
        if not song:
            song = console.input("Song: ")
        _songs = self.search_songs(song)
        song_id, selected_song = self.select_song(_songs)
        self.add_song_to_queue(song_id.split(":")[1])
        rprint(f"Added {selected_song} to queue.")

    def cli_search_artist(self, artist: str, favorites=False):
        if not artist and not favorites:
            artist = console.input("Artist: ")
        while True:
            _artists = self.search_artists(artist)
            if not _artists:
                rprint("No artists found.")
                exit()
            _albums = self.select_albums_by_artists(_artists)
            album_id, selected_album = self.select_album(_albums)
            self.add_album_to_queue(album_id)
            rprint(f"Added {selected_album} to queue.")

    def add_latest_albums_from_favorites(
        self,
        number_of_albums: int,
        random_selection=False,
        random_random=False,
        include_variants=False,
        verbose=False,
    ):
        favorite_artists = self.search_artists()
        if random_selection:
            random.shuffle(favorite_artists)

        added_albums = []
        skipped_albums = []
        for artist in favorite_artists:
            if len(added_albums) >= number_of_albums:
                break

            albums = self.get_albums(artist["id"])
            if not albums:
                continue

            if include_variants:
                if random_random:
                    selected = random.choice(albums)
                else:
                    selected = sorted(albums, key=lambda x: x["date"], reverse=True)[0]
            else:
                selected, skipped = _select_best_album(albums, prefer_latest=not random_random)
                skipped_albums.extend(skipped)

                if not selected:
                    continue

            self.add_album_to_queue(selected["id"])
            added_albums.append(f"{artist['name']}: {selected['title']}")

        rprint(f"[bold green]Added {'random' if random_random else 'latest'} albums:[/bold green]")
        for album in added_albums:
            rprint(f"- {album}")

        if skipped_albums:
            rprint(
                f"[dim](Skipped {len(skipped_albums)} variant albums: deluxe, remix, etc.)[/dim]"
            )
            if verbose:
                rprint("[dim]Skipped albums:[/dim]")
                for album in skipped_albums:
                    rprint(f"[dim]  - {album['artist']}: {album['title']}[/dim]")

    def add_artist_to_favorites(self, artist_id: str):
        """Add an artist to TIDAL favorites"""
        url = f"AddFavourite?service=Tidal&artistid={artist_id}"
        self._make_request(url)

    def remove_artist_from_favorites(self, artist_id: str):
        """Remove an artist from TIDAL favorites"""
        url = f"DeleteFavourite?service=Tidal&artistid={artist_id}"
        self._make_request(url)

    def select_artist_for_favorites(self, artists: list[Any]):
        """Select an artist using fzf with preview of artist info and albums"""
        fzf = FzfPrompt("fzf --tmux 90%,80% --preview 'b pr album {}'")
        try:
            artist_name = fzf.prompt([x["name"] for x in artists])[0]
        except IndexError:
            rprint("No artist found or selected.")
            exit(1)

        # Find the selected artist
        selected_artist = next((x for x in artists if x["name"] == artist_name), None)
        if not selected_artist:
            rprint("Could not find matching artist.")
            exit(1)

        return selected_artist

    def cli_favorite_artist(self, artist: str):
        """Search for artists and add selected one to favorites"""
        if not artist:
            artist = console.input("Artist: ")

        _artists = self.search_artists(artist)
        if not _artists:
            rprint("No artists found.")
            return

        selected_artist = self.select_artist_for_favorites(_artists)

        # Show artist info and albums before adding to favorites
        artist_id = selected_artist["id"]
        artist_name = selected_artist["name"]

        rprint(f"[bold blue]Artist:[/bold blue] {artist_name}")

        # Show artist info
        try:
            artist_info = self.get_artis_info(artist_id)
            rprint(artist_info)
        except Exception:
            rprint("Could not fetch artist info.")

        # Show albums
        try:
            albums = self.get_albums(artist_id)
            rprint(f"[bold green]Albums ({len(albums)}):[/bold green]")
            self.print_albums(albums[:10])  # Show first 10 albums
            if len(albums) > 10:
                rprint(f"... and {len(albums) - 10} more albums")
        except Exception:
            rprint("Could not fetch albums.")

        # Add to favorites
        try:
            self.add_artist_to_favorites(artist_id)
            rprint(f"[bold green]✓ Successfully added '{artist_name}' to favorites![/bold green]")
        except Exception as e:
            rprint(f"[red]✗ Failed to add artist to favorites: {e}[/red]")

    def export_favorite_artists(self):
        """Export all favorite artists"""
        favorite_artists = self.search_artists()
        if not favorite_artists:
            rprint("No favorite artists found.")
            return

        rprint(f"[bold green]Favorite Artists ({len(favorite_artists)}):[/bold green]")
        for artist in favorite_artists:
            rprint(f"{artist['name']}")
