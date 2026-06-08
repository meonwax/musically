from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto

from app.game_config import ScoringConfig

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    LOBBY = auto()
    PLAYING = auto()
    ROUND_RESULT = auto()
    FINISHED = auto()


@dataclass
class Player:
    name: str
    score: int = 0
    correct_songs: int = 0
    correct_artists: int = 0
    correct_years: int = 0


@dataclass
class Track:
    uri: str
    name: str
    artists: list[str]
    year: int | None = None


@dataclass
class RoundGuess:
    player_name: str
    song_guess: str
    artist_guess: str
    year_guess: int | None
    song_correct: bool
    artist_correct: bool
    year_correct: bool
    points: int


@dataclass
class RoundState:
    track: Track
    player_order: list[str]
    guesses: list[RoundGuess] = field(default_factory=list)
    current_player_idx: int = 0

    @property
    def current_player(self) -> str | None:
        if self.current_player_idx < len(self.player_order):
            return self.player_order[self.current_player_idx]
        return None

    @property
    def all_guessed(self) -> bool:
        return self.current_player_idx >= len(self.player_order)


def compute_points(
    song_correct: bool,
    artist_correct: bool,
    year_correct: bool,
    scoring: ScoringConfig,
) -> int:
    base = (scoring.song if song_correct else 0) + (
        scoring.artist if artist_correct else 0
    )
    if year_correct and base > 0:
        return base * scoring.year_multiplier
    return base


_DEFAULT_SCORING = ScoringConfig(song=1, artist=1, year_multiplier=2)


@dataclass
class GameState:
    scoring: ScoringConfig = field(default_factory=lambda: _DEFAULT_SCORING)
    players: list[Player] = field(default_factory=list)
    total_rounds: int = 0  # 0 = endless
    phase: GamePhase = GamePhase.LOBBY

    playlist_tracks: list[Track] = field(default_factory=list)
    available_tracks: list[Track] = field(default_factory=list)

    current_round: RoundState | None = None
    round_number: int = 0

    device_id: str | None = None
    year_enrichment_done: bool = False

    def add_player(self, name: str) -> Player | None:
        if any(p.name == name for p in self.players):
            logger.info("Rejected duplicate player name: %r", name)
            return None
        player = Player(name=name)
        self.players.append(player)
        logger.info("Player added: %r (%d total)", name, len(self.players))
        return player

    def remove_player(self, name: str) -> None:
        if not any(p.name == name for p in self.players):
            logger.info("Remove player ignored, not found: %r", name)
            return
        self.players = [p for p in self.players if p.name != name]
        logger.info("Player removed: %r (%d remaining)", name, len(self.players))

    def set_playlist(self, tracks: list[dict]) -> None:
        self.playlist_tracks = [
            Track(
                uri=t["uri"],
                name=t["name"],
                artists=t["artists"],
                year=t.get("year"),
            )
            for t in tracks
        ]
        self.available_tracks = list(self.playlist_tracks)
        random.shuffle(self.available_tracks)
        logger.info("Playlist set: %d tracks", len(self.playlist_tracks))

    def start_game(self) -> None:
        self.phase = GamePhase.PLAYING
        self.round_number = 0
        for p in self.players:
            p.score = 0
            p.correct_songs = 0
            p.correct_artists = 0
            p.correct_years = 0
        self.available_tracks = list(self.playlist_tracks)
        random.shuffle(self.available_tracks)
        player_names = [p.name for p in self.players]
        logger.info(
            "Game started: players=%s total_rounds=%s",
            player_names,
            self.total_rounds or "endless",
        )

    def start_round(self) -> RoundState | None:
        if not self.available_tracks:
            self.available_tracks = list(self.playlist_tracks)
            random.shuffle(self.available_tracks)

        if not self.available_tracks:
            logger.warning("Cannot start round: no tracks in playlist")
            return None

        track = self.available_tracks.pop()
        self.round_number += 1

        names = [p.name for p in self.players]
        if names:
            start = (self.round_number - 1) % len(names)
            order = names[start:] + names[:start]
        else:
            order = []

        self.current_round = RoundState(track=track, player_order=order)
        self.phase = GamePhase.PLAYING
        logger.info(
            "Round %d started: track=%r artists=%s turn_order=%s",
            self.round_number,
            track.name,
            track.artists,
            order,
        )
        return self.current_round

    def record_guess(
        self,
        player_name: str,
        song_guess: str,
        artist_guess: str,
        year_guess: int | None,
        song_correct: bool,
        artist_correct: bool,
        year_correct: bool,
    ) -> None:
        if self.current_round is None:
            logger.warning("Ignored guess for %r: no active round", player_name)
            return
        pts = compute_points(
            song_correct, artist_correct, year_correct, self.scoring
        )
        self.current_round.guesses.append(
            RoundGuess(
                player_name=player_name,
                song_guess=song_guess,
                artist_guess=artist_guess,
                year_guess=year_guess,
                song_correct=song_correct,
                artist_correct=artist_correct,
                year_correct=year_correct,
                points=pts,
            )
        )
        for p in self.players:
            if p.name == player_name:
                p.score += pts
                if song_correct:
                    p.correct_songs += 1
                if artist_correct:
                    p.correct_artists += 1
                if year_correct:
                    p.correct_years += 1
                break
        self.current_round.current_player_idx += 1
        logger.info(
            "Guess recorded: round=%d player=%r points=%d "
            "song=%s artist=%s year=%s",
            self.round_number,
            player_name,
            pts,
            song_correct,
            artist_correct,
            year_correct,
        )

    def skip_turn(self, player_name: str) -> None:
        logger.info("Turn skipped: round=%d player=%r", self.round_number, player_name)
        self.record_guess(
            player_name,
            song_guess="(skipped)",
            artist_guess="",
            year_guess=None,
            song_correct=False,
            artist_correct=False,
            year_correct=False,
        )

    def finish_round(self) -> None:
        self.phase = GamePhase.ROUND_RESULT
        if self.current_round is None:
            logger.info("Round %d finished", self.round_number)
            return
        track = self.current_round.track
        logger.info(
            "Round %d finished: answer=%r by %s",
            self.round_number,
            track.name,
            ", ".join(track.artists),
        )

    def is_game_over(self) -> bool:
        if self.total_rounds == 0:
            return False  # endless
        return self.round_number >= self.total_rounds

    def end_game(self) -> None:
        self.phase = GamePhase.FINISHED
        leaderboard = self.get_leaderboard()
        if leaderboard:
            scores = ", ".join(f"{p.name}={p.score}" for p in leaderboard)
            logger.info("Game ended after %d rounds: %s", self.round_number, scores)
        else:
            logger.info("Game ended after %d rounds (no players)", self.round_number)

    def get_leaderboard(self) -> list[Player]:
        return sorted(self.players, key=lambda p: p.score, reverse=True)

    def reset(self) -> None:
        logger.info("Game state reset (was phase=%s)", self.phase.name)
        self.players.clear()
        self.playlist_tracks.clear()
        self.available_tracks.clear()
        self.current_round = None
        self.round_number = 0
        self.total_rounds = 0
        self.phase = GamePhase.LOBBY
        self.device_id = None
        self.year_enrichment_done = False
