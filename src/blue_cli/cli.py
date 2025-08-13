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


@click.command(cls=AliasedGroup)
@click.option("--host", default=HOST, help=f"BlueOS host (default: {HOST})")
@click.option("--port", default=PORT, type=int, help=f"BlueOS port (default: {PORT})")
@click.pass_context
def cli(ctx, host, port):
    """Control BlueOS with custom commands"""
    ctx.ensure_object(dict)
    ctx.obj["blue"] = BlueSound(host, port)


@cli.command()
@click.argument("number", default=1, type=int)
@click.pass_context
def random_cmd(ctx, number):
    """Enqueue random albums"""
    ctx.obj["blue"].enqueue_random_albums(number)


@cli.command()
@click.pass_context
def add_list(ctx):
    """Add albums from list"""
    ctx.obj["blue"].add_list_to_queue()


@cli.command()
@click.option("--all", "-a", is_flag=True, help="Clean all queue")
@click.option("--pick", "-p", is_flag=True, help="Interactive album picker for removal")
@click.pass_context
def cleanup(ctx, all, pick):
    """Delete songs from queue until current song"""
    if all:
        ctx.obj["blue"].cleanup_all()
    elif pick:
        ctx.obj["blue"].cleanup_pick()
    else:
        ctx.obj["blue"].cleanup()


@cli.command()
@click.option("--album", "-a", is_flag=True, help="Search albums only")
@click.pass_context
def search_albums(ctx, album):
    """Search for music"""
    if album:
        ctx.obj["blue"].search_albums()
    else:
        ctx.obj["blue"].search()


@cli.group(cls=AliasedGroup)
@click.pass_context
def preview(ctx):
    """Helper for previewing while browsing"""
    ctx.obj["online"] = TidalService(host=HOST, port=PORT)


@preview.command()
@click.argument("album")
@click.pass_context
def tracks(ctx, album):
    """Show album tracks"""
    tracks = ctx.obj["online"].get_album_tracks(album)
    ctx.obj["online"].print_tracks(tracks)


@preview.command()
@click.argument("artist")
@click.pass_context
def album(ctx, artist):
    """Show artist albums"""
    artist_id = ctx.obj["online"].get_artistid(artist)
    albums = ctx.obj["online"].get_albums(artist_id)
    artist_info = ctx.obj["online"].get_artis_info(artist_id)
    rprint(artist_info)
    ctx.obj["online"].print_albums(albums)


@cli.group(cls=AliasedGroup)
@click.pass_context
def online(ctx):
    """Helpers for online subscription"""
    ctx.obj["online"] = TidalService(host=HOST, port=PORT)


@online.command()
@click.argument("keyword", required=False)
@click.option("--album", "-a", is_flag=True, help="Search albums only")
@click.option("--song", "-s", is_flag=True, help="Search songs only")
@click.option("--favorites", "-f", is_flag=True, help="Search favorite artists")
@click.pass_context
def search(ctx, keyword, album, song, favorites):
    """Search online"""
    if album:
        ctx.obj["online"].cli_search_albums(keyword)
    elif song:
        ctx.obj["online"].cli_search_songs(keyword)
    elif favorites:
        ctx.obj["online"].cli_search_artist(
            "",
            True,
        )
    else:
        ctx.obj["online"].cli_search_artist(keyword)


@online.command()
@click.argument("number", default=5, type=int)
@click.option("--random", "-R", is_flag=True, help="Add random albums from favorites")
@click.pass_context
def random(ctx, number, random):
    """Add latest albums from random favorite artists"""
    ctx.obj["online"].add_latest_albums_from_favorites(number, True, random)


@online.command()
@click.argument("number", default=5, type=int)
@click.option("--random", "-R", is_flag=True, help="Add random albums from favorites")
@click.pass_context
def latest(ctx, number, random):
    """Add latest albums from last favorite artists"""
    ctx.obj["online"].add_latest_albums_from_favorites(number, False, random)


@cli.command()
@click.argument("value", type=int, required=False)
@click.pass_context
def volume(ctx, value):
    """Show/Set volume"""
    ctx.obj["blue"].volume(value)


@cli.command()
@click.option("--test", "-t", is_flag=True, help="Test mode: show results without adding to queue")
@click.pass_context
def ai(ctx, test):
    """Get AI recommendations based on current song and add to queue"""
    # Get current playing song
    current_song = ctx.obj["blue"].curent_song_id()
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
@click.pass_context
def next(ctx, album):
    """Skip to next track or next album"""
    if album:
        ctx.obj["blue"].next_album()
    else:
        ctx.obj["blue"].next_song()


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
        @click.pass_context
        def command(ctx):
            getattr(ctx.obj["blue"], func_name)()

        return command

    for cmd_name, cmd_info in SIMPLE_COMMANDS.items():
        # Create command with its help text
        cli.command(name=cmd_name, help=cmd_info["help"])(create_command(cmd_info["func_name"]))


# Register commands
register_simple_commands(cli)
