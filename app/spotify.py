from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass, field

import httpx

from app.config import Settings
from app.game import PlaybackDevice, Track

# The Web Playback SDK registers the browser under this Connect device name.
WEB_PLAYER_NAME = "Musically Game"


@dataclass(frozen=True)
class PlaybackState:
    device_id: str | None
    paused: bool
    position: int


@dataclass
class SpotifyTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # epoch timestamp

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # refresh 60s early


@dataclass
class SpotifyClient:
    settings: Settings
    tokens: SpotifyTokens | None = field(default=None, repr=False)
    _http: httpx.AsyncClient = field(default_factory=httpx.AsyncClient, repr=False)

    def get_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.settings.spotify_client_id,
            "scope": self.settings.spotify_scopes,
            "redirect_uri": self.settings.spotify_redirect_uri,
            "state": state,
        }
        return f"{self.settings.spotify_auth_url}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> SpotifyTokens:
        resp = await self._http.post(
            self.settings.spotify_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.spotify_redirect_uri,
            },
            auth=(
                self.settings.spotify_client_id,
                self.settings.spotify_client_secret,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        self.tokens = SpotifyTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=time.time() + data["expires_in"],
        )
        return self.tokens

    async def refresh_access_token(self) -> None:
        if self.tokens is None:
            raise RuntimeError("No tokens to refresh")
        resp = await self._http.post(
            self.settings.spotify_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.tokens.refresh_token,
            },
            auth=(
                self.settings.spotify_client_id,
                self.settings.spotify_client_secret,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        self.tokens = SpotifyTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", self.tokens.refresh_token),
            expires_at=time.time() + data["expires_in"],
        )

    async def get_access_token(self) -> str:
        if self.tokens is None:
            raise RuntimeError("Not authenticated with Spotify")
        if self.tokens.expired:
            await self.refresh_access_token()
        return self.tokens.access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> httpx.Response:
        token = await self.get_access_token()
        resp = await self._http.request(
            method,
            f"{self.settings.spotify_api_base}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            json=json_body,
        )
        resp.raise_for_status()
        return resp

    async def _api_get(self, path: str, params: dict | None = None) -> dict:
        return (await self._request("GET", path, params=params)).json()

    async def _api_put(
        self,
        path: str,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        return await self._request("PUT", path, params=params, json_body=json_body)

    # ── Playlist ────────────────────────────────────────────────

    @staticmethod
    def extract_playlist_id(url_or_id: str) -> str:
        """Accept a full Spotify URL, URI, or bare playlist ID."""
        m = re.search(r"playlist[/:]([A-Za-z0-9]+)", url_or_id)
        if m:
            return m.group(1)
        # Assume bare ID
        return url_or_id.strip()

    async def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        tracks: list[Track] = []
        path: str | None = f"/playlists/{playlist_id}/items"
        params: dict | None = {
            "limit": 100,
            "fields": "items(item(uri,name,artists(name),album(release_date))),next",
        }
        while path:
            data = await self._api_get(path, params)
            for entry in data.get("items", []):
                t = entry.get("item")
                # Local files and podcast episodes can't be played as tracks.
                if not t or not t.get("uri", "").startswith("spotify:track:"):
                    continue
                release_date = (t.get("album") or {}).get("release_date", "")
                tracks.append(
                    Track(
                        uri=t["uri"],
                        name=t["name"],
                        artists=[a["name"] for a in t.get("artists", [])],
                        year=int(release_date[:4]) if len(release_date) >= 4 else None,
                    )
                )
            next_url = data.get("next")
            if next_url:
                path = next_url.replace(self.settings.spotify_api_base, "")
                params = None  # next URL already includes params
            else:
                path = None
        return tracks

    # ── Playback ────────────────────────────────────────────────

    async def play_track(self, track_uri: str, device_id: str) -> None:
        await self._api_put(
            "/me/player/play",
            json_body={"uris": [track_uri]},
            params={"device_id": device_id},
        )

    async def get_devices(self) -> list[PlaybackDevice]:
        """Spotify Connect devices the game can control, without its own web player."""
        data = await self._api_get("/me/player/devices")
        return [
            PlaybackDevice(
                id=d["id"],
                name=d.get("name", ""),
                type=d.get("type", ""),
            )
            for d in data.get("devices", [])
            if d.get("id")
            and not d.get("is_restricted")
            and d.get("name") != WEB_PLAYER_NAME
        ]

    async def get_playback_state(self) -> PlaybackState | None:
        resp = await self._request("GET", "/me/player")
        if resp.status_code == 204 or not resp.content:
            return None
        data = resp.json()
        device = data.get("device") or {}
        return PlaybackState(
            device_id=device.get("id"),
            paused=not data.get("is_playing", False),
            position=data.get("progress_ms") or 0,
        )

    async def pause(self, device_id: str) -> None:
        await self._api_put("/me/player/pause", params={"device_id": device_id})

    async def resume(self, device_id: str) -> None:
            await self._api_put("/me/player/play", params={"device_id": device_id})
