from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    secret_key: str

    spotify_auth_url: str = "https://accounts.spotify.com/authorize"
    spotify_token_url: str = "https://accounts.spotify.com/api/token"
    spotify_api_base: str = "https://api.spotify.com/v1"

    spotify_scopes: str = (
        "streaming "
        "user-read-playback-state "
        "user-modify-playback-state "
        "user-read-email "
        "user-read-private "
        "playlist-read-private "
        "playlist-read-collaborative"
    )


def get_settings() -> Settings:
    return Settings(
        spotify_client_id=os.environ["SPOTIFY_CLIENT_ID"],
        spotify_client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        spotify_redirect_uri=os.environ.get(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/callback"
        ),
        secret_key=os.environ.get("SECRET_KEY", "change-me"),
    )
