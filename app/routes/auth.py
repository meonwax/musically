from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def is_logged_in(request: Request) -> bool:
    # Tokens live only in memory, so a session cookie can outlive them
    # across server restarts.
    return (
        bool(request.session.get("authenticated"))
        and request.app.state.spotify.tokens is not None
    )


@router.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    url = request.app.state.spotify.get_authorize_url(state)
    logger.info("Spotify login initiated")
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        logger.warning("Spotify OAuth error: %s", error)
        return RedirectResponse(f"/?error={error}")

    saved_state = request.session.get("oauth_state")
    if state != saved_state:
        logger.warning("Spotify OAuth state mismatch")
        return RedirectResponse("/?error=state_mismatch")

    spotify = request.app.state.spotify
    await spotify.exchange_code(code)
    request.session["authenticated"] = True
    logger.info("Spotify authentication successful")
    return RedirectResponse("/lobby")
