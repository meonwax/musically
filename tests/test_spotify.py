from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.spotify import SpotifyClient, SpotifyTokens


class TestExtractPlaylistId:
    def test_bare_id(self):
        assert SpotifyClient.extract_playlist_id("37i9dQZF1DXcBWIGoYBM5M") == "37i9dQZF1DXcBWIGoYBM5M"

    def test_full_url(self):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc"
        assert SpotifyClient.extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_spotify_uri(self):
        uri = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
        assert SpotifyClient.extract_playlist_id(uri) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_url_with_trailing_slash(self):
        url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M/"
        assert SpotifyClient.extract_playlist_id(url) == "37i9dQZF1DXcBWIGoYBM5M"

    def test_strips_whitespace(self):
        assert SpotifyClient.extract_playlist_id("  37i9dQZF1DXcBWIGoYBM5M  ") == "37i9dQZF1DXcBWIGoYBM5M"


class TestSpotifyTokens:
    def test_not_expired(self):
        tokens = SpotifyTokens(
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )
        assert tokens.expired is False

    def test_expired(self):
        tokens = SpotifyTokens(
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() - 100,
        )
        assert tokens.expired is True

    def test_expired_within_buffer(self):
        tokens = SpotifyTokens(
            access_token="token",
            refresh_token="refresh",
            expires_at=time.time() + 30,  # within 60s buffer
        )
        assert tokens.expired is True


class TestAuthorizeUrl:
    def test_contains_client_id(self, spotify_client: SpotifyClient):
        url = spotify_client.get_authorize_url("state123")
        assert "client_id=test_client_id" in url

    def test_contains_state(self, spotify_client: SpotifyClient):
        url = spotify_client.get_authorize_url("mystate")
        assert "state=mystate" in url

    def test_contains_redirect_uri(self, spotify_client: SpotifyClient):
        url = spotify_client.get_authorize_url("state")
        assert "redirect_uri=" in url

    def test_contains_scopes(self, spotify_client: SpotifyClient):
        url = spotify_client.get_authorize_url("state")
        assert "scope=" in url
        assert "streaming" in url

    def test_starts_with_spotify_auth_url(self, spotify_client: SpotifyClient):
        url = spotify_client.get_authorize_url("state")
        assert url.startswith("https://accounts.spotify.com/authorize?")


class TestEnsureToken:
    @pytest.mark.asyncio
    async def test_raises_without_tokens(self, spotify_client: SpotifyClient):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            await spotify_client._ensure_token()

    @pytest.mark.asyncio
    async def test_returns_token_when_valid(self, authenticated_spotify: SpotifyClient):
        token = await authenticated_spotify._ensure_token()
        assert token == "fake_access_token"
