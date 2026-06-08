from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.game import GamePhase, GameState
from app.musicbrainz import enrich_tracks

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
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
    if not request.session.get("authenticated"):
        return RedirectResponse("/")
    game = request.app.state.game
    if game.phase not in (GamePhase.LOBBY, GamePhase.FINISHED):
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


async def _run_enrichment(game) -> None:
    try:
        await enrich_tracks(game.playlist_tracks)
    except Exception:
        logger.exception("Year enrichment failed")
    finally:
        game.year_enrichment_done = True


@router.post("/lobby/set-playlist", response_class=HTMLResponse)
async def set_playlist(request: Request, playlist_url: str = Form(...)):
    spotify = request.app.state.spotify
    game = request.app.state.game
    try:
        playlist_id = spotify.extract_playlist_id(playlist_url)
        tracks = await spotify.get_playlist_tracks(playlist_id)
        if not tracks:
            return templates.TemplateResponse(
                request,
                "partials/messages.html",
                context=_lobby_message_context(
                    game, error="Playlist is empty or not found"
                ),
            )
        game.set_playlist(tracks)
        game.year_enrichment_done = False
        request.app.state.enrichment_task = asyncio.create_task(
            _run_enrichment(game)
        )
        return templates.TemplateResponse(
            request,
            "partials/messages.html",
            context=_lobby_message_context(game),
        )
    except Exception as e:
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
        return RedirectResponse("/lobby?error=Need+at+least+one+player", status_code=303)
    if not game.playlist_tracks:
        return RedirectResponse("/lobby?error=Set+a+playlist+first", status_code=303)

    rounds = int(total_rounds) if total_rounds.isdigit() else 0
    game.total_rounds = rounds
    game.start_game()
    game.start_round()
    return RedirectResponse("/game", status_code=303)
