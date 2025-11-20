#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import time
from dataclasses import dataclass

import jmespath
import xmltodict
from click import ClickException
from pyfzf.pyfzf import FzfPrompt
from requests import get, post
from requests.exceptions import ConnectionError
from rich.progress import Progress

from .console import console
from .playlist_service import PlaylistService

rprint = console.print


@dataclass
class Song:
    artist: str
    title: str
    album: str
    song_id: int
    secs: int | None = None
    totlen: int | None = None

    def __str__(self):
        return f"{self.song_id}: {self.artist} - {self.album} - {self.title}"


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
    ):
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
        url = f"{self.url}/{endpoint}"
        request_func = get if method.upper() == "GET" else post
        try:
            r = request_func(url, params=params, json=json)
        except ConnectionError as err:
            console.show_cursor()
            raise ClickException("Connection error") from err
        if r.status_code != 200:
            console.show_cursor()
            raise ClickException("HTTP Error")
        return r

    def _parse_xml(self, response) -> dict:
        # Handle both Response objects and strings
        xml_text = response.text if hasattr(response, "text") else response
        obj = xmltodict.parse(xml_text, attr_prefix="", dict_constructor=dict)
        if obj is None:
            console.show_cursor()
            raise ClickException("Output parsing error")
        return obj

    def pause(self) -> None:
        self._make_request("Pause", params={"toggle": 1})

    def next_song(self):
        self._make_request("Skip")

    def back(self):
        self._make_request("Back")

    def volume(self, new_volume: int | None):
        r = self._make_request("Status")
        obj = self._parse_xml(r)
        current_volume = jmespath.search("status.volume", obj)
        if not isinstance(current_volume, str):
            raise TypeError
        current_volume = int(current_volume)
        rprint(f"Volume is {current_volume}")
        if new_volume is None:
            return
        if new_volume - current_volume > 5:
            for vol in range(current_volume + 1, new_volume + 1):
                self._make_request("Volume", method="POST", json={"level": vol})
                time.sleep(0.1)
        else:
            self._make_request("Volume", method="POST", json={"level": new_volume})
        rprint(f"Volume new {new_volume}")

    def enqueue_album(self, album_url: str):
        self._make_request(album_url)

    def next_album(self):
        status = self.curent_song_id()
        next_song_id = self.playlist_service.find_next_album_song_id(status.song_id)
        if next_song_id:
            self._make_request("Play", params={"id": next_song_id})

    def show_queue(self):
        s = console.status("Getin queue...")
        s.start()
        status = self.curent_song_id()
        albums = self.playlist_service.get_album_blocks()
        current_album = 1
        s.stop()

        album_no = 1
        for artist, album, _count, _album_id, last_song_id in albums:
            album_display = f"{artist} - {album}"
            if f"{status.artist} - {status.album}" == album_display:
                current_album = album_no
                rprint(f"[red]{album_no:02}/{status.song_id:03}[/] {album_display}")
            else:
                rprint(f"[green]{album_no:02}/{last_song_id:03}[/] {album_display}")
            album_no += 1

        # Get position within album
        playlist = self.playlist_service.get_playlist()
        current_song = playlist.find_song_by_id(status.song_id)
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

    def curent_song_id(self) -> Song:
        r = self._make_request("Status")
        obj = self._parse_xml(r)
        s = jmespath.search("status.[song, album, artist, name, secs, totlen]", obj)
        if not isinstance(s, list):
            raise TypeError
        # Extract optional time fields, converting to int if present
        secs = int(s[4]) if s[4] is not None else None
        totlen = int(s[5]) if s[5] is not None else None
        song = Song(
            artist=s[2],
            title=s[3],
            album=s[1],
            song_id=int(s[0]),
            secs=secs,
            totlen=totlen,
        )  # type: ignore
        return song

    def cleanup(self):
        with Progress(console=console) as progress:
            song = self.curent_song_id()
            rprint(f"Queue played {song.song_id} songs.")
            task = progress.add_task(f"[green]Cleaning {song.song_id} ...", total=song.song_id)
            while not progress.finished:
                song = self.curent_song_id()
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
