from __future__ import annotations

from app.game import (
    GamePhase,
    GameState,
    Player,
    RoundState,
    Track,
    compute_points,
)
from app.game_config import ScoringConfig
from tests.conftest import SAMPLE_TRACKS

DEFAULT_SCORING = ScoringConfig(song=1, artist=1, year_multiplier=2)


class TestPlayer:
    def test_default_score_is_zero(self):
        p = Player(name="Alice")
        assert p.score == 0

    def test_score_increments(self):
        p = Player(name="Alice")
        p.score += 1
        assert p.score == 1


class TestRoundState:
    def _make_round(self, players: list[str]) -> RoundState:
        track = Track(uri="spotify:track:1", name="Test Song", artists=["Artist"], year=2000)
        return RoundState(track=track, player_order=players)

    def test_current_player_returns_first(self):
        rnd = self._make_round(["Alice", "Bob"])
        assert rnd.current_player == "Alice"

    def test_current_player_advances(self):
        rnd = self._make_round(["Alice", "Bob"])
        rnd.current_player_idx = 1
        assert rnd.current_player == "Bob"

    def test_current_player_none_when_done(self):
        rnd = self._make_round(["Alice"])
        rnd.current_player_idx = 1
        assert rnd.current_player is None

    def test_all_guessed_false_initially(self):
        rnd = self._make_round(["Alice", "Bob"])
        assert rnd.all_guessed is False

    def test_all_guessed_true_when_done(self):
        rnd = self._make_round(["Alice"])
        rnd.current_player_idx = 1
        assert rnd.all_guessed is True


class TestComputePoints:
    def test_nothing_correct(self):
        assert compute_points(False, False, False, DEFAULT_SCORING) == 0

    def test_song_only(self):
        assert compute_points(True, False, False, DEFAULT_SCORING) == 1

    def test_artist_only(self):
        assert compute_points(False, True, False, DEFAULT_SCORING) == 1

    def test_song_and_artist(self):
        assert compute_points(True, True, False, DEFAULT_SCORING) == 2

    def test_song_and_year(self):
        assert compute_points(True, False, True, DEFAULT_SCORING) == 2

    def test_artist_and_year(self):
        assert compute_points(False, True, True, DEFAULT_SCORING) == 2

    def test_all_correct(self):
        assert compute_points(True, True, True, DEFAULT_SCORING) == 4

    def test_year_alone_gives_nothing(self):
        assert compute_points(False, False, True, DEFAULT_SCORING) == 0

    def test_custom_scoring(self):
        scoring = ScoringConfig(song=2, artist=3, year_multiplier=4)
        assert compute_points(True, True, True, scoring) == 20


class TestGameStatePlayers:
    def test_add_player(self, game: GameState):
        p = game.add_player("Alice")
        assert p is not None
        assert p.name == "Alice"
        assert len(game.players) == 1

    def test_add_duplicate_player_returns_none(self, game: GameState):
        game.add_player("Alice")
        result = game.add_player("Alice")
        assert result is None
        assert len(game.players) == 1

    def test_add_multiple_players(self, game: GameState):
        game.add_player("Alice")
        game.add_player("Bob")
        assert len(game.players) == 2

    def test_remove_player(self, game: GameState):
        game.add_player("Alice")
        game.add_player("Bob")
        game.remove_player("Alice")
        assert len(game.players) == 1
        assert game.players[0].name == "Bob"

    def test_remove_nonexistent_player_is_noop(self, game: GameState):
        game.add_player("Alice")
        game.remove_player("Nobody")
        assert len(game.players) == 1


class TestGameStatePlaylist:
    def test_set_playlist(self, game: GameState):
        game.set_playlist(SAMPLE_TRACKS)
        assert len(game.playlist_tracks) == 5
        assert len(game.available_tracks) == 5

    def test_set_playlist_creates_track_objects(self, game: GameState):
        game.set_playlist(SAMPLE_TRACKS[:1])
        t = game.playlist_tracks[0]
        assert t.uri == "spotify:track:1"
        assert t.name == "Bohemian Rhapsody"
        assert t.artists == ["Queen"]
        assert t.year == 1975


class TestGameStateRounds:
    def test_start_game_resets_scores(self, game_ready: GameState):
        game_ready.players[0].score = 5
        game_ready.players[0].correct_songs = 2
        game_ready.players[0].correct_artists = 1
        game_ready.players[0].correct_years = 3
        game_ready.start_game()
        assert all(p.score == 0 for p in game_ready.players)
        assert all(p.correct_songs == 0 for p in game_ready.players)
        assert all(p.correct_artists == 0 for p in game_ready.players)
        assert all(p.correct_years == 0 for p in game_ready.players)

    def test_start_game_sets_phase(self, game_ready: GameState):
        game_ready.start_game()
        assert game_ready.phase == GamePhase.PLAYING

    def test_start_round_picks_track(self, game_playing: GameState):
        assert game_playing.current_round is not None
        assert game_playing.current_round.track is not None
        assert game_playing.round_number == 1

    def test_start_round_shuffles_player_order(self, game_playing: GameState):
        rnd = game_playing.current_round
        assert set(rnd.player_order) == {"Alice", "Bob", "Charlie"}

    def test_start_round_no_repeat_tracks(self, game_ready: GameState):
        game_ready.total_rounds = 5
        game_ready.start_game()
        seen_uris = set()
        for _ in range(5):
            rnd = game_ready.start_round()
            assert rnd.track.uri not in seen_uris
            seen_uris.add(rnd.track.uri)

    def test_start_round_recycles_when_exhausted(self, game: GameState):
        game.add_player("Alice")
        game.set_playlist(SAMPLE_TRACKS[:1])
        game.total_rounds = 0
        game.start_game()
        rnd1 = game.start_round()
        assert rnd1 is not None
        rnd2 = game.start_round()
        assert rnd2 is not None

    def test_start_round_returns_none_for_empty_playlist(self, game: GameState):
        game.add_player("Alice")
        game.start_game()
        result = game.start_round()
        assert result is None


class TestGameStateGuessing:
    def _guess(self, game, player, song_ok=False, artist_ok=False, year_ok=False):
        game.record_guess(
            player, "sg", "ag", 2000,
            song_correct=song_ok, artist_correct=artist_ok, year_correct=year_ok,
        )

    def test_record_song_correct(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player, song_ok=True)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 1
        assert p.correct_songs == 1
        assert p.correct_artists == 0
        assert p.correct_years == 0
        assert rnd.guesses[0].song_correct is True
        assert rnd.guesses[0].points == 1

    def test_record_artist_correct(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player, artist_ok=True)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 1
        assert rnd.guesses[0].artist_correct is True

    def test_record_song_and_artist(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player, song_ok=True, artist_ok=True)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 2

    def test_year_doubles_points(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player, song_ok=True, artist_ok=True, year_ok=True)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 4
        assert p.correct_songs == 1
        assert p.correct_artists == 1
        assert p.correct_years == 1
        assert rnd.guesses[0].points == 4

    def test_year_alone_gives_zero(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player, year_ok=True)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 0

    def test_record_wrong_guess(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        self._guess(game_playing, player)
        p = next(p for p in game_playing.players if p.name == player)
        assert p.score == 0

    def test_skip_turn(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        game_playing.skip_turn(player)
        assert rnd.guesses[0].song_guess == "(skipped)"
        assert rnd.guesses[0].points == 0

    def test_record_guess_advances_player(self, game_playing: GameState):
        rnd = game_playing.current_round
        first = rnd.current_player
        self._guess(game_playing, first)
        assert rnd.current_player != first or len(rnd.player_order) == 1

    def test_all_guessed_after_all_players(self, game_playing: GameState):
        rnd = game_playing.current_round
        for _ in range(len(rnd.player_order)):
            self._guess(game_playing, rnd.current_player)
        assert rnd.all_guessed is True

    def test_record_guess_noop_without_round(self, game: GameState):
        game.record_guess("Nobody", "s", "a", None, False, False, False)


class TestGameStateScoring:
    def test_finish_round_sets_phase(self, game_playing: GameState):
        game_playing.finish_round()
        assert game_playing.phase == GamePhase.ROUND_RESULT

    def test_is_game_over_endless(self, game_playing: GameState):
        game_playing.total_rounds = 0
        assert game_playing.is_game_over() is False

    def test_is_game_over_with_limit(self, game_playing: GameState):
        game_playing.total_rounds = 1
        assert game_playing.is_game_over() is True

    def test_is_game_over_not_yet(self, game_playing: GameState):
        game_playing.total_rounds = 5
        assert game_playing.is_game_over() is False

    def test_end_game(self, game_playing: GameState):
        game_playing.end_game()
        assert game_playing.phase == GamePhase.FINISHED

    def test_leaderboard_sorted(self, game_playing: GameState):
        game_playing.players[0].score = 3
        game_playing.players[1].score = 5
        game_playing.players[2].score = 1
        lb = game_playing.get_leaderboard()
        assert lb[0].score == 5
        assert lb[1].score == 3
        assert lb[2].score == 1


class TestGameStateReset:
    def test_reset_clears_everything(self, game_playing: GameState):
        game_playing.reset()
        assert game_playing.players == []
        assert game_playing.playlist_tracks == []
        assert game_playing.available_tracks == []
        assert game_playing.current_round is None
        assert game_playing.round_number == 0
        assert game_playing.total_rounds == 0
        assert game_playing.phase == GamePhase.LOBBY
        assert game_playing.device_id is None
        assert game_playing.year_enrichment_done is False
