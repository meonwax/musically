from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.game import GamePhase, GameState
from app.musicbrainz import enrich_tracks
from app.routes.auth import is_logged_in
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _lobby_status_message(game: GameState) -> str | None:
    if game.playlist_tracks:
        count = len(game.playlist_tracks)
        if game.year_enrichment_done:
            return f"Playlist loaded: {count} tracks. Release years verified."
        return (
            f"Playlist loaded: {count} tracks. "
            "Fetching original release years..."
        )
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
    if game.phase not in (GamePhase.LOBBY, GamePhase.FINISHED):
        logger.info("Lobby entered during %s, resetting game", game.phase.name)
        game.reset()
    game.phase = GamePhase.LOBBY
    return templates.TemplateResponse(
        request,
        "lobby.html",
        context={
            "predefined_playlists": request.app.state.game_config.playlists,
            **_lobby_message_context(
                game, error=request.query_params.get("error")
            ),
        },
    )


@router.post("/lobby/add-player", response_class=HTMLResponse)
async def add_player(request: Request, player_name: str = Form(...)):
    game = request.app.state.game
    name = player_name.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "partials/lobby_player_update.html",
            context=_lobby_message_context(
                game, error="Name cannot be empty"
            ),
        )
    if game.add_player(name) is None:
        return templates.TemplateResponse(
            request,
            "partials/lobby_player_update.html",
            context=_lobby_message_context(
                game, error=f"'{name}' is already taken"
            ),
        )
    return templates.TemplateResponse(
        request,
        "partials/lobby_player_update.html",
        context=_lobby_message_context(game),
    )


@router.post("/lobby/remove-player", response_class=HTMLResponse)
async def remove_player(request: Request, player_name: str = Form(...)):
    game = request.app.state.game
    game.remove_player(player_name)
    return templates.TemplateResponse(
        request,
        "partials/lobby_player_update.html",
        context=_lobby_message_context(game),
    )


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


@router.post("/lobby/set-playlist", response_class=HTMLResponse)
async def set_playlist(request: Request, playlist_url: str = Form(...)):
    spotify = request.app.state.spotify
    game = request.app.state.game
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
        game.set_playlist(tracks)
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
