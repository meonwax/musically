from __future__ import annotations

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    url = request.app.state.spotify.get_authorize_url(state)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/?error={error}")

    saved_state = request.session.get("oauth_state")
    if state != saved_state:
        return RedirectResponse("/?error=state_mismatch")

    spotify = request.app.state.spotify
    await spotify.exchange_code(code)
    request.session["authenticated"] = True
    return RedirectResponse("/lobby")
