from __future__ import annotations

import os

os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/callback")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest

from app.config import Settings
from app.game import GameState, Track
from app.spotify import SpotifyClient, SpotifyTokens


def sample_tracks() -> list[Track]:
    return [
        Track(uri="spotify:track:1", name="Bohemian Rhapsody", artists=["Queen"], year=1975),
        Track(uri="spotify:track:2", name="Stairway to Heaven", artists=["Led Zeppelin"], year=1971),
        Track(uri="spotify:track:3", name="Hotel California", artists=["Eagles"], year=1977),
        Track(uri="spotify:track:4", name="Imagine", artists=["John Lennon"], year=1971),
        Track(uri="spotify:track:5", name="Smells Like Teen Spirit", artists=["Nirvana"], year=1991),
    ]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        spotify_client_id="test_client_id",
        spotify_client_secret="test_client_secret",
        spotify_redirect_uri="http://127.0.0.1:8000/callback",
        secret_key="test-secret-key",
    )


@pytest.fixture
def game() -> GameState:
    return GameState()


@pytest.fixture
def game_with_players(game: GameState) -> GameState:
    game.add_player("Alice")
    game.add_player("Bob")
    game.add_player("Charlie")
    return game


@pytest.fixture
def game_ready(game_with_players: GameState) -> GameState:
    game_with_players.set_playlist(sample_tracks())
    return game_with_players


@pytest.fixture
def game_playing(game_ready: GameState) -> GameState:
    game_ready.total_rounds = 3
    game_ready.start_game()
    game_ready.start_round()
    return game_ready


@pytest.fixture
def spotify_client(settings: Settings) -> SpotifyClient:
    return SpotifyClient(settings=settings)


@pytest.fixture
def authenticated_spotify(spotify_client: SpotifyClient) -> SpotifyClient:
    import time

    spotify_client.tokens = SpotifyTokens(
        access_token="fake_access_token",
        refresh_token="fake_refresh_token",
        expires_at=time.time() + 3600,
    )
    return spotify_client
