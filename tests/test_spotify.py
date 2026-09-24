from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.game import Track
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


class TestGetAccessToken:
    async def test_raises_without_tokens(self, spotify_client: SpotifyClient):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            await spotify_client.get_access_token()

    async def test_returns_token_when_valid(self, authenticated_spotify: SpotifyClient):
        token = await authenticated_spotify.get_access_token()
        assert token == "fake_access_token"


def _entry(uri: str, name: str = "Song", release_date: str = "1985-01-01") -> dict:
    return {
        "item": {
            "uri": uri,
            "name": name,
            "artists": [{"name": "Artist"}],
            "album": {"release_date": release_date},
        }
    }


class TestGetPlaylistTracks:
    async def test_uses_items_endpoint(self, authenticated_spotify: SpotifyClient):
        with patch.object(
            authenticated_spotify, "_api_get", new_callable=AsyncMock,
            return_value={"items": [], "next": None},
        ) as mock_get:
            await authenticated_spotify.get_playlist_tracks("abc")
        assert mock_get.call_args.args[0] == "/playlists/abc/items"

    async def test_parses_tracks(self, authenticated_spotify: SpotifyClient):
        page = {"items": [_entry("spotify:track:1", "Hit", "1985-06-01")], "next": None}
        with patch.object(
            authenticated_spotify, "_api_get", new_callable=AsyncMock, return_value=page
        ):
            tracks = await authenticated_spotify.get_playlist_tracks("abc")
        assert tracks == [
            Track(uri="spotify:track:1", name="Hit", artists=["Artist"], year=1985)
        ]

    async def test_skips_unplayable_items(self, authenticated_spotify: SpotifyClient):
        page = {
            "items": [
                _entry("spotify:track:1"),
                _entry("spotify:local:Artist:Album:Song:180"),
                _entry("spotify:episode:xyz"),
                {"item": None},
            ],
            "next": None,
        }
        with patch.object(
            authenticated_spotify, "_api_get", new_callable=AsyncMock, return_value=page
        ):
            tracks = await authenticated_spotify.get_playlist_tracks("abc")
        assert [t.uri for t in tracks] == ["spotify:track:1"]

    async def test_missing_release_date(self, authenticated_spotify: SpotifyClient):
        page = {"items": [_entry("spotify:track:1", release_date="")], "next": None}
        with patch.object(
            authenticated_spotify, "_api_get", new_callable=AsyncMock, return_value=page
        ):
            tracks = await authenticated_spotify.get_playlist_tracks("abc")
        assert tracks[0].year is None

    async def test_follows_pagination(self, authenticated_spotify: SpotifyClient):
        pages = [
            {
                "items": [_entry("spotify:track:1")],
                "next": "https://api.spotify.com/v1/playlists/abc/items?offset=100",
            },
            {"items": [_entry("spotify:track:2")], "next": None},
        ]
        with patch.object(
            authenticated_spotify, "_api_get", new_callable=AsyncMock, side_effect=pages
        ) as mock_get:
            tracks = await authenticated_spotify.get_playlist_tracks("abc")
        assert [t.uri for t in tracks] == ["spotify:track:1", "spotify:track:2"]
        assert mock_get.call_args_list[1].args == ("/playlists/abc/items?offset=100", None)
