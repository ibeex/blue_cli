#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
from dataclasses import dataclass

import jmespath
import xmltodict
from requests import Response


@dataclass
class PlaylistSong:
    """Represents a song in the playlist"""

    id: int
    artist: str
    album: str
    title: str
    album_id: int

    def __str__(self):
        return f"{self.id:>3}: {self.artist} - {self.album}: {self.title}"


@dataclass
class PlaylistInfo:
    """Container for playlist data"""

    songs: list[PlaylistSong]

    def get_songs_by_album_id(self, album_id: int) -> list[PlaylistSong]:
        """Get all songs from a specific album"""
        return [song for song in self.songs if song.album_id == album_id]

    def get_unique_albums(self) -> list[tuple[str, str, int, int]]:
        """Get unique albums as (artist, album, song_count, album_id)"""
        album_dict = {}
        for song in self.songs:
            key = (song.artist, song.album, song.album_id)
            if key not in album_dict:
                album_dict[key] = 0
            album_dict[key] += 1

        return [
            (artist, album, count, album_id)
            for (artist, album, album_id), count in album_dict.items()
        ]

    def get_albums_with_last_song_id(self) -> list[tuple[str, str, int, int, int]]:
        """Get unique albums as (artist, album, song_count, album_id, last_song_id)"""
        album_dict = {}
        for song in self.songs:
            key = (song.artist, song.album, song.album_id)
            if key not in album_dict:
                album_dict[key] = {"count": 0, "last_song_id": 0}
            album_dict[key]["count"] += 1
            album_dict[key]["last_song_id"] = max(album_dict[key]["last_song_id"], song.id)

        return [
            (artist, album, data["count"], album_id, data["last_song_id"])
            for (artist, album, album_id), data in album_dict.items()
        ]

    def get_contiguous_album_blocks(self) -> list[tuple[str, str, int, int, int]]:
        """Get contiguous album blocks as (artist, album, song_count, album_id, last_song_id)

        Unlike get_albums_with_last_song_id(), this treats each contiguous sequence
        of the same album as a separate entry, so duplicate albums in the queue
        are shown separately.
        """
        if not self.songs:
            return []

        blocks = []
        current_key = (self.songs[0].artist, self.songs[0].album, self.songs[0].album_id)
        block_count = 1
        block_last_id = self.songs[0].id

        for song in self.songs[1:]:
            song_key = (song.artist, song.album, song.album_id)
            if song_key == current_key:
                block_count += 1
                block_last_id = song.id
            else:
                artist, album, album_id = current_key
                blocks.append((artist, album, block_count, album_id, block_last_id))
                current_key = song_key
                block_count = 1
                block_last_id = song.id

        artist, album, album_id = current_key
        blocks.append((artist, album, block_count, album_id, block_last_id))
        return blocks

    def find_song_by_id(self, song_id: int) -> PlaylistSong | None:
        """Find a song by its ID"""
        return next((song for song in self.songs if song.id == song_id), None)

    def find_next_album_song(self, current_song_id: int) -> PlaylistSong | None:
        """Find the first song of the next album after the current song (by position)"""
        # Find current song by position/index, not just by ID
        current_index = None
        for i, song in enumerate(self.songs):
            if song.id == current_song_id:
                current_index = i
                break

        if current_index is None:
            return None

        current_album = self.songs[current_index].album

        # Look forward from current position to find next album
        for i in range(current_index + 1, len(self.songs)):
            if self.songs[i].album != current_album:
                return self.songs[i]

        # If we reached the end, return the first song
        return self.songs[0] if self.songs else None


class PlaylistService:
    """Centralized service for playlist operations"""

    def __init__(self, base_client):
        self.base_client = base_client

    def _make_playlist_request(self) -> Response:
        """Make the Playlist API request"""
        return self.base_client._make_request("Playlist")

    def _parse_playlist_response(self, response: Response) -> PlaylistInfo:
        """Parse playlist XML response into PlaylistInfo"""
        obj = xmltodict.parse(response.text, attr_prefix="", dict_constructor=dict)
        if obj is None:
            from click import ClickException

            from .console import console

            console.show_cursor()
            raise ClickException("Output parsing error")

        # Extract all required fields: id, artist, album, title, albumid
        songs_data = jmespath.search("playlist.song[].[id, art, alb, title, albumid]", obj)

        if not songs_data:
            return PlaylistInfo(songs=[])

        songs = []
        for song_data in songs_data:
            if len(song_data) >= 5:  # Ensure we have all required fields
                song = PlaylistSong(
                    id=int(song_data[0]),
                    artist=song_data[1] or "",
                    album=song_data[2] or "",
                    title=song_data[3] or "",
                    album_id=int(song_data[4]) if song_data[4] else 0,
                )
                songs.append(song)

        return PlaylistInfo(songs=songs)

    def get_playlist(self) -> PlaylistInfo:
        """Get the current playlist"""
        response = self._make_playlist_request()
        return self._parse_playlist_response(response)

    def get_formatted_queue_list(self) -> list[str]:
        """Get playlist formatted for FZF display"""
        playlist = self.get_playlist()
        return [str(song) for song in playlist.songs]

    def get_albums_summary(self) -> list[tuple[str, str, int, int]]:
        """Get unique albums summary"""
        playlist = self.get_playlist()
        return playlist.get_unique_albums()

    def get_albums_with_positions(self) -> list[tuple[str, str, int, int, int]]:
        """Get albums with last song positions"""
        playlist = self.get_playlist()
        return playlist.get_albums_with_last_song_id()

    def get_album_blocks(self) -> list[tuple[str, str, int, int, int]]:
        """Get contiguous album blocks (treats duplicate albums as separate entries)"""
        playlist = self.get_playlist()
        return playlist.get_contiguous_album_blocks()

    def get_albums_up_to_current(
        self, current_song_id: int, current_artist: str, current_album: str
    ) -> list[tuple[str, str, int, int, int]]:
        """Get albums following original show_queue filtering logic"""
        playlist = self.get_playlist()

        # Replicate original logic: iterate through all songs, track first occurrence of each album
        seen_album_ids = set()
        filtered_albums = []

        for song in playlist.songs:
            if song.album_id not in seen_album_ids:
                seen_album_ids.add(song.album_id)

                # For current album, skip if this first song's ID > current song ID
                if song.artist == current_artist and song.album == current_album:
                    if song.id > current_song_id:
                        continue  # Skip this album

                # Use the song ID of the FIRST occurrence (this song), not the max
                first_song_id = song.id
                count = sum(1 for s in playlist.songs if s.album_id == song.album_id)

                filtered_albums.append(
                    (song.artist, song.album, count, song.album_id, first_song_id)
                )

        return filtered_albums

    def find_next_album_song_id(self, current_song_id: int) -> int | None:
        """Find the ID of the first song in the next album"""
        playlist = self.get_playlist()
        next_song = playlist.find_next_album_song(current_song_id)
        return next_song.id if next_song else None
