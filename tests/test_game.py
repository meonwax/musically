from __future__ import annotations

from app.game import (
    MAX_PLAYERS,
    GamePhase,
    GameState,
    PlaybackDevice,
    Player,
    PlayerColor,
    Playlist,
    RoundState,
    Track,
    compute_points,
)
from app.game_config import ScoringConfig
from tests.conftest import sample_tracks

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

    def test_add_player_rejected_when_full(self, game: GameState):
        for i in range(MAX_PLAYERS):
            game.add_player(f"P{i}")
        assert game.is_full
        assert game.add_player("Late") is None
        assert len(game.players) == MAX_PLAYERS


class TestGameStatePlayerColors:
    def test_players_get_distinct_colors_in_order(self, game: GameState):
        for i in range(MAX_PLAYERS):
            game.add_player(f"P{i}")
        assert [p.color for p in game.players] == list(PlayerColor)

    def test_purple_is_not_a_player_color(self):
        assert "purple" not in {c.value for c in PlayerColor}

    def test_removed_players_color_is_reused(self, game_with_players: GameState):
        bob_color = game_with_players.players[1].color
        game_with_players.remove_player("Bob")
        assert game_with_players.add_player("Dave").color == bob_color

    def test_first_free_color_skips_taken_ones(self, game: GameState):
        game.add_player("Alice")
        game.set_player_color("Alice", PlayerColor.ORANGE)
        assert game.add_player("Bob").color == PlayerColor.RED
        assert game.add_player("Charlie").color == PlayerColor.YELLOW

    def test_set_free_color(self, game_with_players: GameState):
        assert game_with_players.set_player_color("Alice", PlayerColor.PINK)
        assert game_with_players.players[0].color == PlayerColor.PINK
        assert PlayerColor.RED in game_with_players.free_colors()

    def test_set_taken_color_is_rejected(self, game_with_players: GameState):
        bob_color = game_with_players.players[1].color
        assert not game_with_players.set_player_color("Alice", bob_color)
        assert game_with_players.players[0].color == PlayerColor.RED

    def test_set_own_color_is_accepted(self, game_with_players: GameState):
        assert game_with_players.set_player_color("Alice", PlayerColor.RED)

    def test_set_color_of_unknown_player_is_noop(self, game_with_players: GameState):
        before = [p.color for p in game_with_players.players]
        assert game_with_players.set_player_color("Nobody", PlayerColor.PINK)
        assert [p.color for p in game_with_players.players] == before

    def test_turn_color_follows_current_player(self, game_playing: GameState):
        colors = {p.name: p.color for p in game_playing.players}
        rnd = game_playing.current_round
        assert game_playing.turn_color == colors[rnd.current_player]
        game_playing.skip_turn()
        assert game_playing.turn_color == colors[rnd.current_player]

    def test_no_turn_color_after_everyone_guessed(self, game_playing: GameState):
        for _ in game_playing.players:
            game_playing.skip_turn()
        assert game_playing.turn_color is None

    def test_no_turn_color_before_game(self, game_with_players: GameState):
        assert game_with_players.turn_color is None


class TestGameStatePlaylist:
    def test_set_playlist(self, game: GameState):
        game.set_playlist(sample_tracks())
        assert len(game.playlist_tracks) == 5

    def test_set_playlist_keeps_its_name_and_link(self, game: GameState):
        game.set_playlist(sample_tracks(), Playlist(id="abc", name="Vice City 80s"))
        assert game.playlist.name == "Vice City 80s"
        assert game.playlist.url == "https://open.spotify.com/playlist/abc"

    def test_reset_forgets_playlist(self, game: GameState):
        game.set_playlist(sample_tracks(), Playlist(id="abc", name="Vice City 80s"))
        game.reset()
        assert game.playlist is None

    def test_set_playlist_resets_enrichment(self, game: GameState):
        game.year_enrichment_done = True
        game.set_playlist(sample_tracks())
        assert game.year_enrichment_done is False

    def test_start_game_fills_available_tracks(self, game_ready: GameState):
        game_ready.start_game()
        assert len(game_ready.available_tracks) == 5

    def test_in_progress_only_while_playing(self, game_ready: GameState):
        assert not game_ready.in_progress
        game_ready.start_game()
        game_ready.start_round()
        assert game_ready.in_progress
        for _ in game_ready.players:
            game_ready.skip_turn()
        assert game_ready.phase == GamePhase.ROUND_RESULT
        assert game_ready.in_progress
        game_ready.end_game()
        assert not game_ready.in_progress

    def test_new_round_has_not_started_playback(self, game_playing: GameState):
        game_playing.current_round.playback_started = True
        assert game_playing.start_round().playback_started is False

    def test_reset_keeps_playback_device(self, game_ready: GameState):
        device = PlaybackDevice(id="d", name="Kitchen", type="Speaker")
        game_ready.playback_device = device
        game_ready.reset()
        assert game_ready.playback_device == device


def _verify_next(tracks) -> Track:
    track = next(tracks)
    track.year_verified = True
    return track


class TestTracksToVerify:
    def test_playlist_order_before_game_starts(self, game_ready: GameState):
        tracks = game_ready.tracks_to_verify()
        verified = [_verify_next(tracks) for _ in range(5)]
        assert verified == game_ready.playlist_tracks
        assert next(tracks, None) is None

    def test_current_round_then_play_order(self, game_ready: GameState):
        game_ready.start_game()
        game_ready.start_round()
        upcoming = list(reversed(game_ready.available_tracks))
        tracks = game_ready.tracks_to_verify()
        assert _verify_next(tracks) is game_ready.current_round.track
        assert [_verify_next(tracks) for _ in range(4)] == upcoming

    def test_game_started_midway_jumps_to_current_round(self, game_ready: GameState):
        tracks = game_ready.tracks_to_verify()
        _verify_next(tracks)
        game_ready.start_game()
        game_ready.start_round()
        current = game_ready.current_round.track
        if current.year_verified:
            game_ready.start_round()
            current = game_ready.current_round.track
        assert _verify_next(tracks) is current

    def test_skips_verified_tracks(self, game_ready: GameState):
        for track in game_ready.playlist_tracks[:4]:
            track.year_verified = True
        tracks = game_ready.tracks_to_verify()
        assert _verify_next(tracks) is game_ready.playlist_tracks[4]
        assert next(tracks, None) is None


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

    def test_start_round_rotates_first_player(self, game_ready: GameState):
        game_ready.start_game()
        rnd1 = game_ready.start_round()
        assert rnd1.player_order == ["Alice", "Bob", "Charlie"]
        rnd2 = game_ready.start_round()
        assert rnd2.player_order == ["Bob", "Charlie", "Alice"]
        rnd3 = game_ready.start_round()
        assert rnd3.player_order == ["Charlie", "Alice", "Bob"]

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
        game.set_playlist(sample_tracks()[:1])
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
    def _player(self, game: GameState, name: str) -> Player:
        return next(p for p in game.players if p.name == name)

    def test_correct_song(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess(rnd.track.name, "", None)
        assert g.song_correct is True
        assert g.points == 1
        p = self._player(game_playing, player)
        assert p.score == 1
        assert p.correct_songs == 1
        assert p.correct_artists == 0
        assert p.correct_years == 0

    def test_correct_artist(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess("", rnd.track.artists[0], None)
        assert g.artist_correct is True
        assert self._player(game_playing, player).score == 1

    def test_song_and_artist(self, game_playing: GameState):
        rnd = game_playing.current_round
        g = game_playing.submit_guess(rnd.track.name, rnd.track.artists[0], None)
        assert g.points == 2

    def test_year_doubles_points(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess(
            rnd.track.name, rnd.track.artists[0], rnd.track.year
        )
        assert g.year_correct is True
        assert g.points == 4
        p = self._player(game_playing, player)
        assert p.score == 4
        assert p.correct_songs == 1
        assert p.correct_artists == 1
        assert p.correct_years == 1

    def test_uses_configured_scoring(self, game_ready: GameState):
        game_ready.scoring = ScoringConfig(song=2, artist=3, year_multiplier=4)
        game_ready.start_game()
        rnd = game_ready.start_round()
        g = game_ready.submit_guess(
            rnd.track.name, rnd.track.artists[0], rnd.track.year
        )
        assert g.points == 20

    def test_year_alone_gives_zero(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess("", "", rnd.track.year)
        assert g.year_correct is True
        assert g.points == 0
        assert self._player(game_playing, player).correct_years == 1

    def test_wrong_guess(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess("zzzz", "zzzz", 1800)
        assert g.points == 0
        assert self._player(game_playing, player).score == 0

    def test_guess_is_attributed_to_current_player(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.submit_guess("x", "", None)
        assert g.player_name == player

    def test_skip_turn(self, game_playing: GameState):
        rnd = game_playing.current_round
        player = rnd.current_player
        g = game_playing.skip_turn()
        assert g.player_name == player
        assert rnd.guesses[0].song_guess == "(skipped)"
        assert rnd.guesses[0].points == 0

    def test_guess_advances_player(self, game_playing: GameState):
        rnd = game_playing.current_round
        first = rnd.current_player
        game_playing.submit_guess("x", "", None)
        assert rnd.current_player != first

    def test_last_guess_finishes_round(self, game_playing: GameState):
        rnd = game_playing.current_round
        for _ in range(len(rnd.player_order) - 1):
            game_playing.submit_guess("x", "", None)
        assert game_playing.phase == GamePhase.PLAYING
        game_playing.skip_turn()
        assert rnd.all_guessed is True
        assert game_playing.phase == GamePhase.ROUND_RESULT

    def test_guess_after_round_complete_is_ignored(self, game_playing: GameState):
        rnd = game_playing.current_round
        for _ in range(len(rnd.player_order)):
            game_playing.skip_turn()
        assert game_playing.submit_guess("x", "", None) is None
        assert game_playing.skip_turn() is None
        assert len(rnd.guesses) == len(rnd.player_order)

    def test_guess_without_round_is_noop(self, game: GameState):
        assert game.submit_guess("s", "a", None) is None
        assert game.skip_turn() is None


class TestGameStateScoring:
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
        assert game_playing.year_enrichment_done is False
