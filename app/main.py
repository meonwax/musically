from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.game import GameState
from app.playlists import load_predefined_playlists
from app.routes import auth, game, lobby
from app.spotify import SpotifyClient

settings = get_settings()

app = FastAPI(title="Musically")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.state.settings = settings
app.state.spotify = SpotifyClient(settings=settings)
app.state.game = GameState()
app.state.predefined_playlists = load_predefined_playlists()

app.include_router(auth.router)
app.include_router(lobby.router)
app.include_router(game.router)

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if request.session.get("authenticated"):
        return templates.TemplateResponse(
            request, "home.html",
            context={"authenticated": True, "error": request.query_params.get("error")},
        )
    return templates.TemplateResponse(
        request, "home.html",
        context={"error": request.query_params.get("error")},
    )
