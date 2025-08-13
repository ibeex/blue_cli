import json
import pickle
import random
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

    @cache.memoize(expire=60 * 60 * 24 * 7)
    def search_albums(self, album: str):
        album_name_url_encoded = urllib.parse.quote(f'"{album}"')
        url = f"Albums?service=Tidal&expr={album_name_url_encoded}"
        albums = []

        while url:
            r = self._make_request(url)
            obj = self._parse_xml(r)
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
        self, number_of_albums: int, random_selection=False, random_random=False
    ):
        # Get favorite artists
        favorite_artists = self.search_artists()
        if random_selection:
            random.shuffle(favorite_artists)

        added_albums = []
        for artist in favorite_artists[:number_of_albums]:
            # Get albums for each artist
            albums = self.get_albums(artist["id"])
            if albums:
                # Pick latest album or random album
                if random_random:
                    _album = random.choice(albums)
                else:
                    _album = sorted(albums, key=lambda x: x["date"], reverse=True)[0]
                # Add to queue
                self.add_album_to_queue(_album["id"])
                added_albums.append(f"{artist['name']}: {_album['title']}")

        # Print summary
        rprint(
            f"[bold green]Added {'random' if random else 'latest'} albums from favorite artists:[/bold green]"
        )
        for album in added_albums:
            rprint(f"- {album}")
