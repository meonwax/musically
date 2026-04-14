from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.game import GamePhase
from app.main import app
from app.spotify import SpotifyTokens
from tests.conftest import SAMPLE_TRACKS


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset game state and inject fake tokens before each test."""
    app.state.game.reset()
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

    def test_add_player(self, authed_client: TestClient):
        with authed_client:
            resp = authed_client.post(
                "/lobby/add-player",
                data={"player_name": "Alice"},
            )
        assert resp.status_code == 200
        assert "Alice" in resp.text

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

    def test_start_game_without_players(self, authed_client: TestClient):
        game = app.state.game
        game.set_playlist(SAMPLE_TRACKS)
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
        game.set_playlist(SAMPLE_TRACKS)
        with authed_client:
            resp = authed_client.post("/lobby/start", data={"total_rounds": "3"})
        assert resp.status_code == 303
        assert resp.headers["location"] == "/game"
        assert game.phase == GamePhase.PLAYING


class TestGameRoutes:
    def _setup_game(self):
        game = app.state.game
        game.add_player("Alice")
        game.add_player("Bob")
        game.set_playlist(SAMPLE_TRACKS)
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
            game.record_guess(
                rnd.current_player, "x", "", None,
                song_correct=False, artist_correct=False, year_correct=False,
            )
        game.finish_round()
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


class TestLeaderboardRoute:
    def test_leaderboard_page(self, authed_client: TestClient):
        game = app.state.game
        game.add_player("Alice")
        game.add_player("Bob")
        game.players[0].score = 5
        game.players[1].score = 3
        game.end_game()
        with authed_client:
            resp = authed_client.get("/leaderboard")
        assert resp.status_code == 200
        assert "Alice" in resp.text
        assert "Bob" in resp.text

    def test_game_redirects_to_leaderboard_when_finished(self, authed_client: TestClient):
        game = app.state.game
        game.add_player("Alice")
        game.end_game()
        with authed_client:
            resp = authed_client.get("/game")
        assert resp.status_code == 307
        assert resp.headers["location"] == "/leaderboard"
