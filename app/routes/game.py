from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.game import GamePhase, GameState
from app.routes.auth import is_logged_in
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


def _htmx_redirect(url: str) -> HTMLResponse:
    # A plain redirect would make HTMX swap the whole target page into the partial.
    return HTMLResponse("", headers={"HX-Redirect": url})


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
        context={"game": game, "round": game.current_round},
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
        return _htmx_redirect("/game")
    year_val = int(year) if year.strip().isdigit() else None
    game.submit_guess(guess, artist, year_val)
    return _guess_area(request, game)


@router.post("/game/skip", response_class=HTMLResponse)
async def skip_turn(request: Request):
    game = request.app.state.game
    if not _round_is_open(game):
        return _htmx_redirect("/game")
    game.skip_turn()
    return _guess_area(request, game)


@router.post("/game/next-round")
async def next_round(request: Request):
    game = request.app.state.game
    if game.is_game_over():
        logger.info("Last round complete, ending game")
        game.end_game()
        return RedirectResponse("/leaderboard", status_code=303)
    game.start_round()
    return RedirectResponse("/game", status_code=303)


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


@router.post("/game/play-track")
async def play_track(request: Request, device_id: str = Form(...)):
    game = request.app.state.game
    if game.current_round:
        track = game.current_round.track
        logger.info(
            "Playback requested: round=%d device=%s track=%r",
            game.round_number,
            device_id,
            track.name,
        )
        await request.app.state.spotify.play_track(track.uri, device_id)
    return HTMLResponse("")
