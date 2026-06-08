from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.game import GamePhase
from app.matching import check_artist, check_guess, check_year

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/game", response_class=HTMLResponse)
async def game_page(request: Request):
    game = request.app.state.game
    if game.phase == GamePhase.LOBBY:
        return RedirectResponse("/lobby")
    if game.phase == GamePhase.FINISHED:
        return RedirectResponse("/leaderboard")

    settings = request.app.state.settings
    spotify = request.app.state.spotify
    token = await spotify.get_access_token_for_sdk()

    return templates.TemplateResponse(
        request, "game.html",
        context={
            "game": game,
            "round": game.current_round,
            "spotify_token": token,
            "client_id": settings.spotify_client_id,
        },
    )


@router.get("/game/guess-form", response_class=HTMLResponse)
async def guess_form(request: Request):
    game = request.app.state.game
    return templates.TemplateResponse(
        request, "partials/guess_form.html",
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
    rnd = game.current_round
    if rnd is None or rnd.all_guessed:
        return RedirectResponse("/game", status_code=303)

    player_name = rnd.current_player
    song_ok = check_guess(guess, rnd.track.name) if guess.strip() else False
    artist_ok = check_artist(artist, rnd.track.artists) if artist.strip() else False
    year_val = int(year) if year.strip().isdigit() else None
    year_ok = check_year(year_val, rnd.track.year)

    game.record_guess(
        player_name,
        song_guess=guess,
        artist_guess=artist,
        year_guess=year_val,
        song_correct=song_ok,
        artist_correct=artist_ok,
        year_correct=year_ok,
    )

    if rnd.all_guessed:
        game.finish_round()
        return templates.TemplateResponse(
            request, "partials/round_result.html",
            context={"game": game, "round": rnd},
        )

    return templates.TemplateResponse(
        request, "partials/guess_form.html",
        context={"game": game, "round": rnd},
    )


@router.post("/game/skip", response_class=HTMLResponse)
async def skip_turn(request: Request):
    game = request.app.state.game
    rnd = game.current_round
    if rnd is None or rnd.all_guessed:
        return RedirectResponse("/game", status_code=303)

    player_name = rnd.current_player
    game.skip_turn(player_name)

    if rnd.all_guessed:
        game.finish_round()
        return templates.TemplateResponse(
            request, "partials/round_result.html",
            context={"game": game, "round": rnd},
        )

    return templates.TemplateResponse(
        request, "partials/guess_form.html",
        context={"game": game, "round": rnd},
    )


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
    spotify = request.app.state.spotify
    token = await spotify.get_access_token_for_sdk()
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
    spotify = request.app.state.spotify
    game.device_id = device_id
    if game.current_round:
        track = game.current_round.track
        logger.info(
            "Playback requested: round=%d device=%s track=%r",
            game.round_number,
            device_id,
            track.name,
        )
        await spotify.play_track(track.uri, device_id)
    return HTMLResponse("")
