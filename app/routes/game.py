from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.game import GamePhase, GameState
from app.routes.auth import is_logged_in
from app.routes.htmx import htmx_redirect
from app.spotify import WEB_PLAYER_NAME
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def _guess_area(request: Request, game: GameState) -> HTMLResponse:
    if game.phase == GamePhase.ROUND_RESULT:
        name = "partials/round_result.html"
    else:
        name = "partials/guess_form.html"
    return templates.TemplateResponse(
        request, name,
        context={"game": game, "round": game.current_round},
    )


def _round_is_open(game: GameState) -> bool:
    return game.current_round is not None and not game.current_round.all_guessed


@router.get("/game", response_class=HTMLResponse)
async def game_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/")
    game = request.app.state.game
    if game.phase == GamePhase.LOBBY:
        return RedirectResponse("/lobby")
    if game.phase == GamePhase.FINISHED:
        return RedirectResponse("/leaderboard")
    return templates.TemplateResponse(
        request, "game.html",
        context={
            "game": game,
            "round": game.current_round,
            "web_player_name": WEB_PLAYER_NAME,
        },
    )


@router.post("/game/guess", response_class=HTMLResponse)
async def submit_guess(
    request: Request,
    guess: str = Form(""),
    artist: str = Form(""),
    year: str = Form(""),
):
    game = request.app.state.game
    if not _round_is_open(game):
        return htmx_redirect("/game")
    year_val = int(year) if year.strip().isdigit() else None
    game.submit_guess(guess, artist, year_val)
    return _guess_area(request, game)


@router.post("/game/skip", response_class=HTMLResponse)
async def skip_turn(request: Request):
    game = request.app.state.game
    if not _round_is_open(game):
        return htmx_redirect("/game")
    game.skip_turn()
    return _guess_area(request, game)


@router.post("/game/next-round", response_class=HTMLResponse)
async def next_round(request: Request):
    game = request.app.state.game
    if game.phase != GamePhase.ROUND_RESULT:
        # Repeated click after the next round already started: keep the page.
        return HTMLResponse("", status_code=204)
    if game.is_game_over():
        logger.info("Last round complete, ending game")
        game.end_game()
        return htmx_redirect("/leaderboard")
    game.start_round()
    return templates.TemplateResponse(
        request, "partials/round.html",
        context={"game": game, "round": game.current_round, "autoplay": True},
    )


@router.post("/game/end")
async def end_game(request: Request):
    game = request.app.state.game
    game.end_game()
    return RedirectResponse("/leaderboard", status_code=303)


@router.get("/game/token")
async def get_token(request: Request):
    if not is_logged_in(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    token = await request.app.state.spotify.get_access_token()
    return {"access_token": token}


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    game = request.app.state.game
    return templates.TemplateResponse(
        request, "leaderboard.html",
        context={"game": game, "leaderboard": game.get_leaderboard()},
    )


async def _resume_position(
    request: Request, track_uri: str, device_id: str
) -> int | None:
    """Where to continue a track after a page reload; None if it still plays."""
    try:
        state = await request.app.state.spotify.get_playback_state()
    except Exception:
        logger.exception("Reading the playback state failed")
        return 0
    if state is None or state.track_uri != track_uri:
        return 0
    if state.device_id == device_id:
        return None
    # The browser player got a new device on reload; move the track over.
    return state.position


@router.post("/game/play-track")
async def play_track(request: Request, device_id: str = Form("")):
    game = request.app.state.game
    rnd = game.current_round
    # Empty when a round is swapped in before the player is ready; the
    # player's "ready" handler starts playback in that case.
    if rnd is None or not device_id:
        return HTMLResponse("")
    track = rnd.track
    position = 0
    if rnd.playback_started:
        position = await _resume_position(request, track.uri, device_id)
        if position is None:
            logger.info("Page reloaded, track still playing on %s", device_id)
            return HTMLResponse("")
    logger.info(
        "Playback requested: round=%d device=%s track=%r position=%d",
        game.round_number,
        device_id,
        track.name,
        position,
    )
    try:
        await request.app.state.spotify.play_track(track.uri, device_id, position)
    except Exception:
        logger.exception("Starting playback failed on device %s", device_id)
        return HTMLResponse("", status_code=502)
    rnd.playback_started = True
    return HTMLResponse("")


async def _control_device(
    request: Request, command: Callable[[str], Awaitable[None]]
) -> Response:
    if not is_logged_in(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    device = request.app.state.game.playback_device
    if device is None:
        return JSONResponse({"error": "no Spotify device selected"}, status_code=409)
    try:
        await command(device.id)
    except Exception:
        logger.exception("Spotify command failed on %r", device.name)
        return JSONResponse({"error": "Spotify rejected the command"}, status_code=502)
    return Response(status_code=204)


@router.get("/game/playback")
async def playback_state(request: Request):
    if not is_logged_in(request):
        return JSONResponse({"error": "not logged in"}, status_code=401)
    device = request.app.state.game.playback_device
    if device is None:
        return JSONResponse({"error": "no Spotify device selected"}, status_code=409)
    try:
        state = await request.app.state.spotify.get_playback_state()
    except Exception:
        logger.exception("Reading the playback state failed")
        return JSONResponse({"error": "Spotify request failed"}, status_code=502)
    if state is None or state.device_id != device.id:
        return JSONResponse(None)
    return {"paused": state.paused, "position": state.position}


@router.post("/game/pause")
async def pause(request: Request):
    return await _control_device(request, request.app.state.spotify.pause)


@router.post("/game/resume")
async def resume(request: Request):
    return await _control_device(request, request.app.state.spotify.resume)
