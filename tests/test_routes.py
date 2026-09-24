from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.game import GamePhase, GameState
from app.main import app
from app.routes.lobby import _restart_enrichment, _run_enrichment
from app.spotify import SpotifyTokens
from tests.conftest import sample_tracks


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset game state and inject fake tokens before each test."""
    app.state.game.reset()
    app.state.enrichment_task = None
    app.state.spotify.tokens = SpotifyTokens(
        access_token="fake_token",
        refresh_token="fake_refresh",
        expires_at=time.time() + 3600,
    )
    yield
    app.state.game.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def authed_client(client: TestClient) -> TestClient:
    """A client with an authenticated session."""
    with client:
        client.cookies.clear()
        with patch.object(app.state.spotify, "exchange_code", new_callable=AsyncMock):
            resp = client.get("/login")
            assert resp.status_code == 307

            import urllib.parse
            redirect_url = resp.headers["location"]
            parsed = urllib.parse.urlparse(redirect_url)
            params = urllib.parse.parse_qs(parsed.query)
            state = params["state"][0]

            resp = client.get(f"/callback?code=fake_code&state={state}")
            assert resp.status_code == 307
            assert resp.headers["location"] == "/lobby"

    return client


class TestHomeRoute:
    def test_home_page(self, client: TestClient):
        with client:
            resp = client.get("/")
        assert resp.status_code == 200
        assert "Musically" in resp.text

    def test_home_shows_login(self, client: TestClient):
        with client:
            resp = client.get("/")
        assert "Login with Spotify" in resp.text

    def test_home_links_to_lobby_when_logged_in(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.get("/")
        assert "Go to Lobby" in resp.text
        assert "Login with Spotify" not in resp.text

    def test_home_shows_login_when_tokens_lost(self, authed_client: TestClient):
        app.state.spotify.tokens = None
        with authed_client:
            resp = authed_client.get("/")
        assert "Login with Spotify" in resp.text


class TestAuthRoutes:
    def test_login_redirects_to_spotify(self, client: TestClient):
        with client:
            resp = client.get("/login")
        assert resp.status_code == 307
        assert "accounts.spotify.com/authorize" in resp.headers["location"]

    def test_callback_with_error(self, client: TestClient):
        with client:
            resp = client.get("/callback?error=access_denied")
        assert resp.status_code == 307
        assert "error=access_denied" in resp.headers["location"]

    def test_callback_state_mismatch(self, client: TestClient):
        with client:
            resp = client.get("/callback?code=abc&state=wrong")
        assert resp.status_code == 307
        assert "state_mismatch" in resp.headers["location"]

    def test_callback_success(self, client: TestClient):
        with client:
            with patch.object(app.state.spotify, "exchange_code", new_callable=AsyncMock):
                login_resp = client.get("/login")
                import urllib.parse
                redirect_url = login_resp.headers["location"]
                parsed = urllib.parse.urlparse(redirect_url)
                params = urllib.parse.parse_qs(parsed.query)
                state = params["state"][0]

                resp = client.get(f"/callback?code=fake_code&state={state}")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/lobby"


class TestLobbyRoutes:
    def test_lobby_redirects_without_auth(self, client: TestClient):
        with client:
            resp = client.get("/lobby")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/"

    def test_lobby_accessible_when_authed(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.get("/lobby")
        assert resp.status_code == 200
        assert "Game Lobby" in resp.text
        assert "Rolling Stone 500 Best Songs Of All Time" in resp.text
        assert "Choose a playlist" in resp.text
        assert "Loading playlist..." in resp.text
        assert 'hx-disabled-elt="#playlist-setup, #lobby-controls"' in resp.text
        assert "Add at least one player to start." in resp.text
        assert '<button type="submit" disabled>Start Game</button>' in resp.text

    def test_lobby_redirects_when_tokens_lost(self, authed_client: TestClient):
        """Server restart: session cookie survives, in-memory tokens don't."""
        app.state.spotify.tokens = None
        with authed_client:
            resp = authed_client.get("/lobby")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/"

    def test_set_playlist(self, authed_client: TestClient):
        with (
            patch.object(
                app.state.spotify, "get_playlist_tracks",
                new_callable=AsyncMock, return_value=sample_tracks(),
            ),
            patch("app.routes.lobby.enrich_tracks", new_callable=AsyncMock),
            authed_client,
        ):
            resp = authed_client.post(
                "/lobby/set-playlist", data={"playlist_url": "spotify:playlist:abc"}
            )
        assert resp.status_code == 200
        assert "5 tracks" in resp.text
        assert "Fetching original release years" in resp.text
        assert len(app.state.game.playlist_tracks) == 5

    def test_set_playlist_without_playable_tracks(self, authed_client: TestClient):
        with (
            patch.object(
                app.state.spotify, "get_playlist_tracks",
                new_callable=AsyncMock, return_value=[],
            ),
            authed_client,
        ):
            resp = authed_client.post(
                "/lobby/set-playlist", data={"playlist_url": "spotify:playlist:abc"}
            )
        assert "Playlist is empty or not found" in resp.text
        assert app.state.game.playlist_tracks == []

    def test_set_playlist_api_error(self, authed_client: TestClient):
        with (
            patch.object(
                app.state.spotify, "get_playlist_tracks",
                new_callable=AsyncMock, side_effect=RuntimeError("boom"),
            ),
            authed_client,
        ):
            resp = authed_client.post(
                "/lobby/set-playlist", data={"playlist_url": "spotify:playlist:abc"}
            )
        assert "boom" in resp.text

    def test_enrichment_status_done(self, authed_client: TestClient):
        game = app.state.game
        game.set_playlist(sample_tracks())
        game.year_enrichment_done = True
        with authed_client:
            resp = authed_client.get("/lobby/enrichment-status")
        assert "5 tracks. Release years verified." in resp.text
        assert "hx-get=\"/lobby/enrichment-status\"" not in resp.text

    def test_add_player(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.post(
                "/lobby/add-player",
                data={"player_name": "Alice"},
            )
        assert resp.status_code == 200
        assert "Alice" in resp.text
        assert '<button type="submit">Start Game</button>' in resp.text
        assert "Add at least one player to start." not in resp.text

    def test_add_duplicate_player(self, authed_client: TestClient):
        with authed_client:
            authed_client.post("/lobby/add-player", data={"player_name": "Alice"})
            resp = authed_client.post("/lobby/add-player", data={"player_name": "Alice"})
        assert "already taken" in resp.text

    def test_remove_player(self, authed_client: TestClient):
        with authed_client:
            authed_client.post("/lobby/add-player", data={"player_name": "Alice"})
            resp = authed_client.post(
                "/lobby/remove-player",
                data={"player_name": "Alice"},
            )
        assert resp.status_code == 200
        assert "Alice" not in resp.text
        assert '<button type="submit" disabled>Start Game</button>' in resp.text

    def test_start_game_without_players(self, authed_client: TestClient):
        game = app.state.game
        game.set_playlist(sample_tracks())
        with authed_client:
            resp = authed_client.post("/lobby/start", data={"total_rounds": "5"})
        assert resp.status_code == 303
        assert "error" in resp.headers["location"]

    def test_start_game_without_playlist(self, authed_client: TestClient):
        app.state.game.add_player("Alice")
        with authed_client:
            resp = authed_client.post("/lobby/start", data={"total_rounds": "5"})
        assert resp.status_code == 303
        assert "error" in resp.headers["location"]

    def test_start_game_success(self, authed_client: TestClient):
        game = app.state.game
        game.add_player("Alice")
        game.set_playlist(sample_tracks())
        with authed_client:
            resp = authed_client.post("/lobby/start", data={"total_rounds": "3"})
        assert resp.status_code == 303
        assert resp.headers["location"] == "/game"
        assert game.phase == GamePhase.PLAYING


class TestEnrichmentTask:
    @staticmethod
    def _fake_app() -> SimpleNamespace:
        return SimpleNamespace(state=SimpleNamespace(enrichment_task=None))

    async def test_run_marks_done(self):
        game = GameState()
        game.set_playlist(sample_tracks())
        with patch("app.routes.lobby.enrich_tracks", new_callable=AsyncMock):
            await _run_enrichment(game)
        assert game.year_enrichment_done is True

    async def test_run_marks_done_even_on_failure(self):
        game = GameState()
        with patch(
            "app.routes.lobby.enrich_tracks",
            new_callable=AsyncMock, side_effect=RuntimeError("boom"),
        ):
            await _run_enrichment(game)
        assert game.year_enrichment_done is True

    async def test_new_playlist_cancels_previous_run(self):
        fake_app = self._fake_app()
        game = GameState()
        started = asyncio.Event()

        async def slow_enrich(tracks):
            started.set()
            await asyncio.sleep(3600)

        with patch("app.routes.lobby.enrich_tracks", side_effect=slow_enrich):
            game.set_playlist(sample_tracks())
            _restart_enrichment(fake_app, game)
            first = fake_app.state.enrichment_task
            await started.wait()

            started.clear()
            game.set_playlist(sample_tracks()[:2])
            _restart_enrichment(fake_app, game)
            await started.wait()

        assert first.cancelled()
        assert game.year_enrichment_done is False
        fake_app.state.enrichment_task.cancel()


class TestGameRoutes:
    def _setup_game(self):
        game = app.state.game
        game.add_player("Alice")
        game.add_player("Bob")
        game.set_playlist(sample_tracks())
        game.total_rounds = 3
        game.start_game()
        game.start_round()
        return game

    def test_game_redirects_to_lobby_if_not_playing(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.get("/game")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/lobby"

    def test_game_page_when_playing(self, authed_client: TestClient):
        self._setup_game()
        with authed_client:
            resp = authed_client.get("/game")
        assert resp.status_code == 200
        assert "Round 1" in resp.text

    def test_game_page_does_not_leak_answer(self, authed_client: TestClient):
        game = self._setup_game()
        with authed_client:
            resp = authed_client.get("/game")
        assert game.current_round.track.name not in resp.text

    def test_game_redirects_home_without_login(self, client: TestClient):
        self._setup_game()
        with client:
            resp = client.get("/game")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/"

    def test_guess_after_round_complete_uses_hx_redirect(
        self, authed_client: TestClient
    ):
        game = self._setup_game()
        for _ in range(len(game.current_round.player_order)):
            game.skip_turn()
        with authed_client:
            resp = authed_client.post("/game/guess", data={"guess": "x"})
        assert resp.status_code == 200
        assert resp.headers["HX-Redirect"] == "/game"

    def test_submit_guess_song_only(self, authed_client: TestClient):
        game = self._setup_game()
        rnd = game.current_round
        with authed_client:
            resp = authed_client.post(
                "/game/guess",
                data={"guess": "wrong answer", "artist": "", "year": ""},
            )
        assert resp.status_code == 200
        assert len(rnd.guesses) == 1
        assert rnd.guesses[0].points == 0

    def test_submit_guess_with_artist_and_year(self, authed_client: TestClient):
        game = self._setup_game()
        rnd = game.current_round
        track = rnd.track
        with authed_client:
            resp = authed_client.post(
                "/game/guess",
                data={
                    "guess": track.name,
                    "artist": track.artists[0],
                    "year": str(track.year) if track.year else "",
                },
            )
        assert resp.status_code == 200
        g = rnd.guesses[0]
        assert g.song_correct is True
        assert g.artist_correct is True
        if track.year:
            assert g.year_correct is True
            assert g.points == 4
        else:
            assert g.points == 2

    def test_skip_turn(self, authed_client: TestClient):
        game = self._setup_game()
        rnd = game.current_round
        with authed_client:
            resp = authed_client.post("/game/skip")
        assert resp.status_code == 200
        assert rnd.guesses[0].song_guess == "(skipped)"
        assert rnd.guesses[0].points == 0

    def test_all_guesses_shows_result(self, authed_client: TestClient):
        game = self._setup_game()
        rnd = game.current_round
        with authed_client:
            for _ in range(len(rnd.player_order)):
                resp = authed_client.post(
                    "/game/guess",
                    data={"guess": "wrong", "artist": "", "year": ""},
                )
        assert game.phase == GamePhase.ROUND_RESULT
        assert "Answer" in resp.text or "Result" in resp.text

    def test_next_round(self, authed_client: TestClient):
        game = self._setup_game()
        rnd = game.current_round
        for _ in range(len(rnd.player_order)):
            game.skip_turn()
        with authed_client:
            resp = authed_client.post("/game/next-round")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/game"
        assert game.round_number == 2

    def test_end_game(self, authed_client: TestClient):
        self._setup_game()
        with authed_client:
            resp = authed_client.post("/game/end")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/leaderboard"
        assert app.state.game.phase == GamePhase.FINISHED

    def test_get_token(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.get("/game/token")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["access_token"] == "fake_token"

    def test_get_token_requires_login(self, client: TestClient):
        with client:
            resp = client.get("/game/token")
        assert resp.status_code == 401

    def test_play_track(self, authed_client: TestClient):
        game = self._setup_game()
        with (
            patch.object(
                app.state.spotify, "play_track", new_callable=AsyncMock
            ) as mock_play,
            authed_client,
        ):
            resp = authed_client.post("/game/play-track", data={"device_id": "dev1"})
        assert resp.status_code == 200
        mock_play.assert_awaited_once_with(game.current_round.track.uri, "dev1")


class TestLeaderboardRoute:
    def test_leaderboard_page(self, authed_client: TestClient):
        game = app.state.game
        game.add_player("Alice")
        game.add_player("Bob")
        game.players[0].score = 5
        game.players[0].correct_songs = 2
        game.players[0].correct_artists = 3
        game.players[0].correct_years = 1
        game.players[1].score = 3
        game.players[1].correct_songs = 1
        game.players[1].correct_artists = 1
        game.players[1].correct_years = 0
        game.end_game()
        with authed_client:
            resp = authed_client.get("/leaderboard")
        assert resp.status_code == 200
        assert "Alice" in resp.text
        assert "Bob" in resp.text
        assert "Songs" in resp.text
        assert "Artists" in resp.text
        assert "Years" in resp.text

    def test_game_redirects_to_leaderboard_when_finished(self, authed_client: TestClient):
        game = app.state.game
        game.add_player("Alice")
        game.end_game()
        with authed_client:
            resp = authed_client.get("/game")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/leaderboard"
