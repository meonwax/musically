from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.game import GameState
from app.game_config import load_game_config
from app.logging_config import configure_logging
from app.middleware import RequestLoggingMiddleware
from app.routes import auth, game, lobby
from app.routes.auth import is_logged_in
from app.spotify import SpotifyClient
from app.templating import templates

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
game_config = load_game_config()

logger.info(
    "Starting Musically (%d playlists, scoring song=%d artist=%d year×%d)",
    len(game_config.playlists),
    game_config.points.song,
    game_config.points.artist,
    game_config.points.year_multiplier,
)

app = FastAPI(title="Musically")
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.spotify_redirect_uri.startswith("https://"),
)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.state.settings = settings
app.state.game_config = game_config
app.state.spotify = SpotifyClient(settings=settings)
app.state.game = GameState(scoring=game_config.points)
app.state.enrichment_task = None

app.include_router(auth.router)
app.include_router(lobby.router)
app.include_router(game.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request, "home.html",
        context={
            "logged_in": is_logged_in(request),
            "error": request.query_params.get("error"),
        },
    )
