from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.game import (
    MAX_PLAYERS,
    GamePhase,
    GameState,
    PlaybackDevice,
    PlayerColor,
    Playlist,
)
from app.game_config import PredefinedPlaylist
from app.musicbrainz import enrich_tracks
from app.routes.auth import is_logged_in
from app.routes.htmx import htmx_redirect
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _lobby_status_message(game: GameState) -> str | None:
    if game.playlist_tracks:
        count = len(game.playlist_tracks)
        loaded = (
            f'Playlist "{game.playlist.name}" loaded' if game.playlist
            else "Playlist loaded"
        )
        if game.year_enrichment_done:
            return f"{loaded}: {count} tracks. Release years verified."
        return f"{loaded}: {count} tracks. Fetching original release years..."
    if not game.players:
        return "Add at least one player to start."
    return None


def _lobby_message_context(
    game: GameState,
    *,
    error: str | None = None,
    message: str | None = None,
    message_type: str = "status",
) -> dict:
    if error:
        return {
            "game": game,
            "message": error,
            "message_type": "error",
            "enrichment_pending": False,
        }
    if message is None:
        message = _lobby_status_message(game)
    return {
        "game": game,
        "message": message,
        "message_type": message_type,
        "enrichment_pending": bool(game.playlist_tracks)
        and not game.year_enrichment_done,
    }


@router.get("/lobby", response_class=HTMLResponse)
async def lobby(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/")
    game = request.app.state.game
    if game.in_progress:
        # Back button or a stale tab; the game only ends via "End Game".
        logger.info("Lobby requested during %s, back to game", game.phase.name)
        return RedirectResponse("/game")
    game.phase = GamePhase.LOBBY
    loaded = game.playlist and _predefined_playlist(request, game.playlist.id)
    return templates.TemplateResponse(
        request,
        "lobby.html",
        context={
            "predefined_playlists": request.app.state.game_config.playlists,
            "selected_playlist_url": loaded.url if loaded else None,
            **_lobby_message_context(
                game, error=request.query_params.get("error")
            ),
        },
    )


def _back_to_game() -> HTMLResponse:
    """Refuse a lobby change sent from a stale lobby page mid-game."""
    logger.info("Lobby change refused: game in progress")
    return htmx_redirect("/game")


def _player_update(
    request: Request,
    game: GameState,
    *,
    error: str | None = None,
    focus_player_input: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/lobby_player_update.html",
        context={
            **_lobby_message_context(game, error=error),
            "focus_player_input": focus_player_input,
        },
    )


@router.post("/lobby/add-player", response_class=HTMLResponse)
async def add_player(request: Request, player_name: str = Form(...)):
    game = request.app.state.game
    if game.in_progress:
        return _back_to_game()
    name = player_name.strip()
    error = None
    if not name:
        error = "Name cannot be empty"
    elif game.is_full:
        error = f"The game is full ({MAX_PLAYERS} players max)"
    elif game.add_player(name) is None:
        error = f"'{name}' is already taken"
    return _player_update(request, game, error=error, focus_player_input=True)


@router.post("/lobby/remove-player", response_class=HTMLResponse)
async def remove_player(request: Request, player_name: str = Form(...)):
    game = request.app.state.game
    if game.in_progress:
        return _back_to_game()
    game.remove_player(player_name)
    return _player_update(request, game)


@router.post("/lobby/set-player-color", response_class=HTMLResponse)
async def set_player_color(
    request: Request, player_name: str = Form(...), color: str = Form(...)
):
    game = request.app.state.game
    if game.in_progress:
        return _back_to_game()
    try:
        choice = PlayerColor(color)
    except ValueError:
        return _player_update(request, game, error=f"Unknown color '{color}'")
    if not game.set_player_color(player_name, choice):
        return _player_update(
            request, game, error=f"{choice.title()} is already taken"
        )
    return _player_update(request, game)


async def _run_enrichment(game: GameState) -> None:
    try:
        await enrich_tracks(game.tracks_to_verify())
    except Exception:
        logger.exception("Year enrichment failed")
    # Not in a `finally`: a cancelled run must not mark a newer playlist done.
    game.year_enrichment_done = True
    logger.info(
        "Year enrichment complete for %d tracks",
        len(game.playlist_tracks),
    )


def _restart_enrichment(app: FastAPI, game: GameState) -> None:
    previous: asyncio.Task | None = app.state.enrichment_task
    if previous is not None and not previous.done():
        logger.info("Cancelling year enrichment for previous playlist")
        previous.cancel()
    app.state.enrichment_task = asyncio.create_task(_run_enrichment(game))


def _predefined_playlist(
    request: Request, playlist_id: str
) -> PredefinedPlaylist | None:
    spotify = request.app.state.spotify
    return next(
        (
            p for p in request.app.state.game_config.playlists
            if spotify.extract_playlist_id(p.url) == playlist_id
        ),
        None,
    )


def _playlist(request: Request, playlist_id: str) -> Playlist:
    predefined = _predefined_playlist(request, playlist_id)
    name = predefined.name if predefined else "Custom playlist"
    return Playlist(id=playlist_id, name=name)


@router.post("/lobby/set-playlist", response_class=HTMLResponse)
async def set_playlist(request: Request, playlist_url: str = Form(...)):
    spotify = request.app.state.spotify
    game = request.app.state.game
    if game.in_progress:
        return _back_to_game()
    try:
        playlist_id = spotify.extract_playlist_id(playlist_url)
        tracks = await spotify.get_playlist_tracks(playlist_id)
        if not tracks:
            logger.warning("Playlist empty or not found: %s", playlist_id)
            return templates.TemplateResponse(
                request,
                "partials/messages.html",
                context=_lobby_message_context(
                    game,
                    error="Playlist is empty or not found. In Development "
                    "Mode, Spotify only returns playlists you own or "
                    "collaborate on.",
                ),
            )
        game.set_playlist(tracks, _playlist(request, playlist_id))
        _restart_enrichment(request.app, game)
        return templates.TemplateResponse(
            request,
            "partials/messages.html",
            context=_lobby_message_context(game),
        )
    except Exception as e:
        logger.exception("Failed to load playlist from %r", playlist_url)
        return templates.TemplateResponse(
            request,
            "partials/messages.html",
            context=_lobby_message_context(game, error=str(e)),
        )


async def _device_picker(
    request: Request,
    *,
    devices: list[PlaybackDevice] | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if devices is None:
        try:
            devices = await request.app.state.spotify.get_devices()
        except Exception:
            logger.exception("Failed to list Spotify devices")
            devices = []
            error = error or (
                "Could not load your Spotify devices. "
                "Log in again if this keeps happening."
            )
    return templates.TemplateResponse(
        request,
        "partials/device_picker.html",
        context={
            "devices": devices,
            "selected": request.app.state.game.playback_device,
            "error": error,
        },
    )


@router.get("/lobby/devices", response_class=HTMLResponse)
async def list_devices(request: Request):
    return await _device_picker(request)


@router.post("/lobby/set-device", response_class=HTMLResponse)
async def set_device(request: Request, device_id: str = Form("")):
    game = request.app.state.game
    if game.in_progress:
        return _back_to_game()
    if not device_id:
        game.playback_device = None
        logger.info("Playback device: browser")
        return await _device_picker(request)
    try:
        devices = await request.app.state.spotify.get_devices()
    except Exception:
        logger.exception("Failed to list Spotify devices")
        return await _device_picker(
            request, devices=[], error="Could not load your Spotify devices."
        )
    device = next((d for d in devices if d.id == device_id), None)
    if device is None:
        return await _device_picker(
            request,
            devices=devices,
            error="That device is no longer available. Open Spotify on it "
            "and refresh the list.",
        )
    game.playback_device = device
    logger.info("Playback device: %r (%s)", device.name, device.type)
    return await _device_picker(request, devices=devices)


@router.get("/lobby/enrichment-status", response_class=HTMLResponse)
async def enrichment_status(request: Request):
    game = request.app.state.game
    return templates.TemplateResponse(
        request,
        "partials/messages_oob.html",
        context=_lobby_message_context(game),
    )


@router.post("/lobby/start")
async def start_game(request: Request, total_rounds: str = Form("0")):
    game = request.app.state.game
    if game.in_progress:
        logger.info("Start game refused: game in progress")
        return RedirectResponse("/game", status_code=303)
    if len(game.players) < 1:
        logger.warning("Start game rejected: no players")
        return RedirectResponse("/lobby?error=Need+at+least+one+player", status_code=303)
    if not game.playlist_tracks:
        logger.warning("Start game rejected: no playlist")
        return RedirectResponse("/lobby?error=Set+a+playlist+first", status_code=303)

    rounds = int(total_rounds) if total_rounds.isdigit() else 0
    game.total_rounds = rounds
    game.start_game()
    game.start_round()
    return RedirectResponse("/game", status_code=303)
