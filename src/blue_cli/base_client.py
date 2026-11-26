#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import time
from dataclasses import dataclass

import jmespath
import xmltodict
from pyfzf.pyfzf import FzfPrompt
from requests import Response, get, post
from requests.exceptions import ConnectionError as RequestsConnectionError
from rich.progress import Progress

from .console import console
from .errors import BlueOSError
from .playlist_service import PlaylistService

rprint = console.print


@dataclass(frozen=True, slots=True)
class Song:
    artist: str
    title: str
    album: str
    song_id: int
    secs: int | None = None
    totlen: int | None = None
    album_id: int | None = None

    def __str__(self):
        return f"{self.song_id}: {self.artist} - {self.album} - {self.title}"


@dataclass(frozen=True, slots=True)
class PlayerState:
    """Point-in-time player state from a single Status request."""

    song: Song | None
    volume: int | None
    state: str | None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def format_time(seconds: int) -> str:
    """Format seconds as M:SS or MM:SS time string"""
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


class BluesoundBaseClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"

        self.playlist_service = PlaylistService(self)

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict | None = None,
        json: dict | None = None,
    ) -> Response:
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
        url = f"{self.url}/{endpoint}"
        request_func = get if method.upper() == "GET" else post
        try:
            r = request_func(url, params=params, json=json, timeout=15)
        except RequestsConnectionError as err:
            raise BlueOSError(f"Could not connect to BlueOS at {self.url}") from err
        if r.status_code != 200:
            raise BlueOSError(f"BlueOS returned HTTP {r.status_code} for {endpoint}")
        return r

    def _parse_xml(self, response: Response | str) -> dict:
        # Handle both Response objects and strings
        xml_text = response.text if isinstance(response, Response) else response
        obj = xmltodict.parse(xml_text, attr_prefix="", dict_constructor=dict)
        if obj is None:
            raise BlueOSError("Could not parse BlueOS response")
        return obj

    def get_status(self) -> dict:
        """Return the raw parsed Status response."""
        return self._parse_xml(self._make_request("Status"))

    @staticmethod
    def _parse_song(status: dict) -> Song | None:
        s = jmespath.search("status.[song, album, artist, name, secs, totlen, albumid]", status)
        if not isinstance(s, list) or len(s) < 4:
            return None

        song_id = _optional_int(s[0])
        title = s[3]
        if song_id is None or not title:
            return None

        return Song(
            artist=str(s[2] or ""),
            title=str(title),
            album=str(s[1] or ""),
            song_id=song_id,
            secs=_optional_int(s[4]),
            totlen=_optional_int(s[5]),
            album_id=_optional_int(s[6]) if len(s) > 6 else None,
        )

    def get_current_song(self) -> Song | None:
        """Return the currently playing song, or None when nothing is playing."""
        return self._parse_song(self.get_status())

    def get_player_state(self) -> PlayerState:
        """Return song, volume, and playback state from a single Status request."""
        status = self.get_status()
        volume = _optional_int(jmespath.search("status.volume", status))
        state_value = jmespath.search("status.state", status)
        state = state_value if isinstance(state_value, str) else None
        if state == "play":
            state = "playing"
        elif state == "pause":
            state = "paused"
        elif state == "stop":
            state = "stopped"
        return PlayerState(song=self._parse_song(status), volume=volume, state=state)

    def pause(self) -> None:
        """Toggle between playing and paused."""
        self._make_request("Pause", params={"toggle": 1})

    def play(self) -> None:
        """Start or resume playback of the current queue."""
        self._make_request("Play")

    def stop(self) -> None:
        """Stop playback without clearing the queue."""
        self._make_request("Stop")

    def next_song(self):
        self._make_request("Skip")

    def back(self):
        self._make_request("Back")

    def get_volume(self) -> int:
        volume = self.get_player_state().volume
        if volume is None:
            raise BlueOSError("BlueOS did not report a volume level")
        return volume

    def set_volume(self, new_volume: int) -> None:
        current_volume = self.get_volume()
        if new_volume == current_volume:
            return
        if abs(new_volume - current_volume) > 5:
            step = 1 if new_volume > current_volume else -1
            for vol in range(current_volume + step, new_volume + step, step):
                self._make_request("Volume", method="POST", json={"level": vol})
                time.sleep(0.1)
        else:
            self._make_request("Volume", method="POST", json={"level": new_volume})

    def volume(self, new_volume: int | None):
        current_volume = self.get_volume()
        rprint(f"Volume is {current_volume}")
        if new_volume is None:
            return
        self.set_volume(new_volume)
        rprint(f"Volume new {new_volume}")

    def enqueue_album(self, album_url: str):
        self._make_request(album_url)

    def get_album_art_url(self, album_id: int | str) -> str:
        return f"{self.url}/Artwork?service=Tidal&albumid={album_id}"

    def next_album(self) -> bool:
        current_song = self.get_current_song()
        if current_song is None:
            return False
        next_song_id = self.playlist_service.find_next_album_song_id(current_song.song_id)
        if next_song_id is None:
            return False
        self._make_request("Play", params={"id": next_song_id})
        return True

    def show_queue(self):
        s = console.status("Getin queue...")
        s.start()
        status = self.current_song_id()
        albums = self.playlist_service.get_album_blocks()

        # Get current song to retrieve album_id for matching
        playlist = self.playlist_service.get_playlist()
        current_song = playlist.find_song_by_id(status.song_id)
        current_album = 1
        s.stop()

        album_no = 1
        for artist, album, _count, album_id, last_song_id in albums:
            album_display = f"{artist} - {album}"
            # Match by album_id to handle multi-artist albums correctly
            if current_song and current_song.album_id == album_id:
                current_album = album_no
                rprint(f"[red]{album_no:02}/{status.song_id:03}[/] {album_display}")
            else:
                rprint(f"[green]{album_no:02}/{last_song_id:03}[/] {album_display}")
            album_no += 1

        # Get position within album
        album_position_display = ""
        if current_song:
            album_songs = playlist.get_songs_by_album_id(current_song.album_id)
            position = next((i + 1 for i, s in enumerate(album_songs) if s.id == status.song_id), 0)
            total = len(album_songs)
            album_position_display = f" Song {position}/{total}"

        # Build time/progress display if available
        time_display = ""
        if status.secs is not None and status.totlen is not None:
            current_time = format_time(status.secs)
            total_time = format_time(status.totlen)
            percentage = int((status.secs / status.totlen) * 100) if status.totlen > 0 else 0
            time_display = f" [{current_time} / {total_time} ({percentage}%)]"

        rprint(
            f"Playing Album No. [red]{current_album}[/]{album_position_display} "
            f"{status.album}: {status.title} - {status.artist}{time_display}"
        )

    def cleanup_all(self):
        self._make_request("Clear", params={"id": 0})
        rprint("Queue cleaned up.")

    def current_song_id(self) -> Song:
        song = self.get_current_song()
        if song is None:
            raise BlueOSError("No song is currently playing")
        return song

    def cleanup(self):
        with Progress(console=console) as progress:
            song = self.current_song_id()
            rprint(f"Queue played {song.song_id} songs.")
            task = progress.add_task(f"[green]Cleaning {song.song_id} ...", total=song.song_id)
            while not progress.finished:
                song = self.current_song_id()
                progress.update(task, advance=1, description=f"[green]Cleaning {song.song_id} ...")
                if song.song_id == 0:
                    break
                self._make_request("Delete", params={"id": 0})
        rprint("Queue cleaned up.")

    def get_queue_albums(self) -> list[tuple[str, str, int, int]]:
        """Get albums from queue with format: (artist, album, song_count, album_id)"""
        return self.playlist_service.get_albums_summary()

    def cleanup_album(self, target_album_id: int):
        """Remove all songs from a specific album in the queue"""
        with Progress(console=console) as progress:
            task = progress.add_task("[green]Removing album from queue...", total=None)

            while True:
                playlist = self.playlist_service.get_playlist()
                if not playlist.songs:
                    break

                # Find the first song from the target album (by position, not song_id)
                position_to_delete = None
                for position, song in enumerate(playlist.songs):
                    if song.album_id == target_album_id:
                        position_to_delete = position
                        break

                if position_to_delete is None:
                    break  # No more songs from this album

                # Delete the song at the found position
                self._make_request("Delete", params={"id": position_to_delete})
                progress.advance(task)

        rprint("Album removed from queue.")

    def cleanup_pick(self):
        """Interactive album picker for queue cleanup"""
        albums = self.get_queue_albums()

        if not albums:
            rprint("Queue is empty.")
            return

        # Format albums for fzf display: "Artist - Album (X songs)"
        formatted_albums = []
        album_id_map = {}

        for artist, album, count, album_id in albums:
            display_text = f"{artist} - {album} ({count} songs)"
            formatted_albums.append(display_text)
            album_id_map[display_text] = album_id

        try:
            fzf = FzfPrompt("fzf --tmux 90%,80% --prompt='Select album to remove> '")
            selected_album = fzf.prompt(formatted_albums)[0]

            # Get the album_id for the selected album
            target_album_id = album_id_map[selected_album]

            rprint(f"Removing: {selected_album}")
            self.cleanup_album(target_album_id)

        except (IndexError, KeyboardInterrupt):
            rprint("No album selected.")
            return
