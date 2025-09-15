import functools
import shutil

import click

from .ai_service import AIRecommendationService
from .config import HOST, PORT
from .console import console
from .tidal_service import TidalService
from .usb_service import UsbService as BlueSound

FZF_AVAILABLE = shutil.which("fzf") is not None
rprint = console.print

if not FZF_AVAILABLE:
    rprint("can't find [bold red]fzf[/] executable")
    rprint("install [bold red]fzf[/]")
    exit(1)


class AliasedGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail(f"Too many matches: {', '.join(sorted(matches))}")

    def resolve_command(self, ctx, args):
        # always return the full command name
        _, cmd, args = super().resolve_command(ctx, args)
        if isinstance(cmd, None.__class__):
            return None, None, args
        return cmd.name, cmd, args


def with_blue_service(func):
    """Decorator to inject BlueSound service into command"""

    @click.option("--host", default=HOST, help=f"BlueOS host (default: {HOST})")
    @click.option("--port", default=PORT, type=int, help=f"BlueOS port (default: {PORT})")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        host = kwargs.pop("host")
        port = kwargs.pop("port")
        blue = BlueSound(host, port)
        return func(blue, *args, **kwargs)

    return wrapper


def with_tidal_service(func):
    """Decorator to inject TidalService into command"""

    @click.option("--host", default=HOST, help=f"BlueOS host (default: {HOST})")
    @click.option("--port", default=PORT, type=int, help=f"BlueOS port (default: {PORT})")
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        host = kwargs.pop("host")
        port = kwargs.pop("port")
        tidal = TidalService(host=host, port=port)
        return func(tidal, *args, **kwargs)

    return wrapper


@click.command(cls=AliasedGroup)
def cli():
    """Control BlueOS with custom commands"""
    pass


@cli.command()
@click.argument("number", default=1, type=int)
@with_blue_service
def random_cmd(blue: BlueSound, number):
    """Enqueue random albums"""
    blue.enqueue_random_albums(number)


@cli.command()
@with_blue_service
def add_list(blue: BlueSound):
    """Add albums from list"""
    blue.add_list_to_queue()


@cli.command()
@click.option("--all", "-a", is_flag=True, help="Clean all queue")
@click.option("--pick", "-p", is_flag=True, help="Interactive album picker for removal")
@with_blue_service
def cleanup(blue: BlueSound, all, pick):
    """Delete songs from queue until current song"""
    if all:
        blue.cleanup_all()
    elif pick:
        blue.cleanup_pick()
    else:
        blue.cleanup()


@cli.command()
@click.option("--album", "-a", is_flag=True, help="Search albums only")
@with_blue_service
def search_albums(blue: BlueSound, album):
    """Search for music"""
    if album:
        blue.search_albums()
    else:
        blue.search()


@cli.group(cls=AliasedGroup)
def preview():
    """Helper for previewing while browsing"""
    pass


@preview.command()
@click.argument("album")
@with_tidal_service
def tracks(tidal: TidalService, album):
    """Show album tracks"""
    tracks = tidal.get_album_tracks(album)
    tidal.print_tracks(tracks)


@preview.command()
@click.argument("artist")
@with_tidal_service
def album(tidal: TidalService, artist):
    """Show artist albums"""
    artist_id = tidal.get_artistid(artist)
    albums = tidal.get_albums(artist_id)
    artist_info = tidal.get_artis_info(artist_id)
    rprint(artist_info)
    tidal.print_albums(albums)


@cli.group(cls=AliasedGroup)
def online():
    """Helpers for online subscription"""
    pass


@online.command()
@click.argument("keyword", required=False)
@click.option("--album", "-a", is_flag=True, help="Search albums only")
@click.option("--song", "-s", is_flag=True, help="Search songs only")
@click.option("--favorites", "-f", is_flag=True, help="Search favorite artists")
@with_tidal_service
def search(tidal: TidalService, keyword, album, song, favorites):
    """Search online"""
    if album:
        tidal.cli_search_albums(keyword)
    elif song:
        tidal.cli_search_songs(keyword)
    elif favorites:
        tidal.cli_search_artist(
            "",
            True,
        )
    else:
        tidal.cli_search_artist(keyword)


@online.command()
@click.argument("number", default=5, type=int)
@click.option("--random", "-R", is_flag=True, help="Randomize album selection")
@with_tidal_service
def random(tidal: TidalService, number, random):
    """Add latest albums from random favorite artists"""
    tidal.add_latest_albums_from_favorites(number, True, random)


@online.command()
@click.argument("number", default=5, type=int)
@click.option("--random", "-R", is_flag=True, help="Randomize album selection")
@with_tidal_service
def latest(tidal: TidalService, number, random):
    """Add latest albums from last favorite artists"""
    tidal.add_latest_albums_from_favorites(number, False, random)


@cli.command()
@click.argument("value", type=int, required=False)
@with_blue_service
def volume(blue: BlueSound, value):
    """Show/Set volume"""
    blue.volume(value)


@cli.command()
@click.option("--test", "-t", is_flag=True, help="Test mode: show results without adding to queue")
@with_blue_service
def ai(blue: BlueSound, test):
    """Get AI recommendations based on current song and add to queue"""
    # Get current playing song
    current_song = blue.curent_song_id()
    artist = current_song.artist
    album = current_song.album

    # Use AI service to get recommendations and enqueue albums
    ai_service = AIRecommendationService(host=HOST, port=PORT)
    if test:
        ai_service.get_recommendations_test_mode(artist, album)
    else:
        ai_service.get_recommendations_and_enqueue(artist, album)


@cli.command()
@click.option("--album", "-a", is_flag=True, help="Skip to next album")
@with_blue_service
def next(blue: BlueSound, album):
    """Skip to next track or next album"""
    if album:
        blue.next_album()
    else:
        blue.next_song()


SIMPLE_COMMANDS = {
    "queue": {
        "func_name": "show_queue",
        "help": "Show the current queue",
    },
    "pause": {
        "func_name": "pause",
        "help": "Pause/Resume playback",
    },
    "back": {
        "func_name": "back",
        "help": "Go to previous track",
    },
    "list": {
        "func_name": "list",
        "help": "Show playlist",
    },
}


def register_simple_commands(cli: click.Group) -> None:
    """Register all simple commands to the CLI group."""

    def create_command(func_name):
        @with_blue_service
        def command(blue: BlueSound):
            getattr(blue, func_name)()

        return command

    for cmd_name, cmd_info in SIMPLE_COMMANDS.items():
        # Create command with its help text
        cli.command(name=cmd_name, help=cmd_info["help"])(create_command(cmd_info["func_name"]))


# Register commands
register_simple_commands(cli)
