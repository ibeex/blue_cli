#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import html
import json
import random
import sys
from pathlib import Path
from typing import Any

import jmespath
from pyfzf.pyfzf import FzfPrompt
from requests import get

from .base_client import BluesoundBaseClient
from .config import MEDIA_LOCATION
from .console import console

rprint = console.print


class Cachefmanager:
    def __init__(self) -> None:
        self.cache_file = self.get_cache_file()

    def get_cache_file(self) -> Path:
        cache_dir = Path.home() / ".cache" / "mpdrandom"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "cache.json"

    def get_cache_size(self, no_albums: int, percent: int = 65) -> int:
        cache_size: int = int(no_albums / 100 * percent)
        if no_albums <= 1:
            cache_size = 0
        elif cache_size == 0:
            cache_size = 1
        return cache_size

    def load_cache(self, cache_file: Path) -> list[str]:
        json_cache: str = ""
        if not cache_file.is_file():
            return []
        with cache_file.open() as f:
            json_cache = f.read()
        return json.loads(json_cache)

    def save_cache(self, cache_file, cache):
        with cache_file.open(mode="w") as f:
            f.write(json.dumps(cache, indent=4, sort_keys=True))

    def enforce_cache_size(self, size: int, cache: list[Any]) -> list[Any]:
        if len(cache) > size:
            return cache[len(cache) - size :]
        return cache


class UsbService(BluesoundBaseClient):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(host, port)
        self.cache_manager = Cachefmanager()

    def get_usb_service(self) -> str:
        r = self._make_request("Browse")
        obj = self._parse_xml(r.text)
        key = jmespath.search(f"browse.item[?text=='{MEDIA_LOCATION}'].browseKey", obj)
        if not isinstance(key, list):
            raise KeyError
        if not isinstance(key[0], str):
            raise KeyError
        return key[0]

    def search(self):
        s = console.status("Gathering artist...")
        s.start()
        albums = self.all_albums()
        artists = sorted(set([x["Artist"] for x in albums]))
        fzf = FzfPrompt("fzf --tmux 90%,80%")
        s.stop()
        while True:
            try:
                artist = fzf.prompt(artists)[0]
            except IndexError:
                rprint("No artist found or selected.")
                exit(1)
            albums_artist = sorted(set([x["Album"] for x in albums if x["Artist"] == artist]))
            try:
                artist_albums = fzf.prompt(albums_artist, "--multi")
            except ImportError:
                rprint("No album found or selected.")
                exit(1)
            for album in artist_albums:
                album_url = [x for x in albums if x["Artist"] == artist and x["Album"] == album][0][
                    "url"
                ]
                self.enqueue_album(album_url)
                rprint(f"{artist}: {album} [green]Added[/]")

    def search_albums(self):
        s = console.status("Gathering albums...")
        s.start()
        albums = self.all_albums()
        only_albums = sorted(set([x["Album"] for x in albums]))
        fzf = FzfPrompt("fzf --tmux 90%,80%")
        s.stop()
        while True:
            try:
                selected_albums = fzf.prompt(only_albums, "--multi")
            except IndexError:
                rprint("No album found.")
                exit(1)
            if not selected_albums:
                rprint("No album selected.")
                exit(1)
            for album in selected_albums:
                album_url = [x for x in albums if x["Album"] == album][0]["url"]
                self.enqueue_album(album_url)
                print(f"Added {album} to queue.")

    def all_albums(self) -> list[dict]:
        all_albums = []
        usb_key = self.get_usb_service()
        r = self._make_request("Browse", params={"key": usb_key})
        obj = self._parse_xml(r.text)
        key = jmespath.search("browse.item[?text=='Albums'].browseKey", obj)
        if not isinstance(key, list):
            raise KeyError
        if not isinstance(key[0], str):
            raise KeyError
        r = self._make_request("Browse", params={"key": key[0]})
        obj = self._parse_xml(r.text)
        keys = jmespath.search("browse.item[].browseKey", obj)
        if not isinstance(keys, list):
            raise KeyError
        for part in keys:
            if not isinstance(part, str):
                raise KeyError
            r = self._make_request("Browse", params={"key": part})
            obj = self._parse_xml(r.text)
            albums = jmespath.search(
                'browse.item[].{"url": playURL, "Artist": text2, "Album": text}', obj
            )
            if not isinstance(albums, list):
                raise KeyError
            for album in albums:
                if not isinstance(album, dict):
                    raise KeyError
                album["url"] = album["url"].replace("playnow=1", "playnow=-1&where=last")  # type: ignore
                all_albums.append(album)
        return all_albums

    def enqueue_random_albums(self, number_off_albums: int):
        albums = self.all_albums()
        cache_file = self.cache_manager.get_cache_file()
        cache = self.cache_manager.load_cache(cache_file)
        cache_size = self.cache_manager.get_cache_size(len(albums))
        for _ in range(number_off_albums):
            while True:
                random_album = random.choice(albums)
                album_url: str = random_album["url"]
                random_album = f"{random_album['Album']}: {random_album['Artist']}"
                if random_album in cache:
                    continue
                break
            cache.append(random_album)
            self.enqueue_album(album_url)
            rprint(f"{random_album} [green]Added[/]")
        rprint(f"{len(albums)} albums and [green]{len(cache)}[/] items in cache.")
        cache = self.cache_manager.enforce_cache_size(cache_size, cache)
        self.cache_manager.save_cache(cache_file, cache)

    @staticmethod
    def list_from_stdin() -> list[str]:
        return [x.strip() for x in sys.stdin]

    def add_album_at_end(self, title: str, art: str, usb_key: str) -> None:
        self._make_request(
            "Add",
            params={
                "service": usb_key[:-1],
                "album": html.unescape(title),  # type: ignore
                "artist": html.unescape(art),  # type: ignore
                "playnow": "-1",
                "where": "last",
            },
        )

    def list(self):
        s = console.status("Getin queue...")
        s.start()
        albums = self.playlist_service.get_formatted_queue_list()
        status = self.curent_song_id()
        s.stop()
        fzf = FzfPrompt(
            f'fzf --tiebreak=index --tmux 90%,80% --prompt="{status.song_id} {status.artist}> "'
        )
        try:
            song = fzf.prompt(albums)[0]
        except IndexError:
            rprint("No song found or selected.")
            exit(1)
        next_album = song.split(":")[0].strip()
        _ = get(f"{self.url}/Play", params={"id": next_album})

    def next_album(self):
        """Skip to the next album"""
        current_song = self.curent_song_id()
        next_song_id = self.playlist_service.find_next_album_song_id(current_song.song_id)
        if next_song_id:
            self._make_request("Play", params={"id": next_song_id})

    def add_list_to_queue(self):
        def get_album_url(albums, artist, album):
            found_abums = []
            for data in albums:
                if album == data["Album"]:
                    found_abums.append(data)
            if found_abums and len(found_abums) == 1:
                return found_abums[0]["url"]
            elif found_abums and len(found_abums) > 1:
                for _album in found_abums:
                    if _album["Artist"] in artist or artist in _album["Artist"]:
                        return _album["url"]
                rprint(found_abums)
                return ""
            else:
                return ""

        list_of_albums = self.list_from_stdin()
        random.shuffle(list_of_albums)

        added = 0
        all_albums = self.all_albums()

        for line in list_of_albums:
            artist = line.split("-")[0].strip()
            album = line.split("-")[1].strip()
            album_url = get_album_url(all_albums, artist, album)
            if not album_url:
                rprint(f"{artist}: {album}", "[red]FAIL[/]")
                continue

            get(self.url + album_url)
            rprint(f"{artist}: {album} [green]Added[/]")
            added += 1
        rprint(f"Added [green]{added}[/] albums")
