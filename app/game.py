from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto


class GamePhase(Enum):
    LOBBY = auto()
    PLAYING = auto()
    ROUND_RESULT = auto()
    FINISHED = auto()


@dataclass
class Player:
    name: str
    score: int = 0


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
    song_correct: bool, artist_correct: bool, year_correct: bool
) -> int:
    base = (1 if song_correct else 0) + (1 if artist_correct else 0)
    if year_correct and base > 0:
        return base * 2
    return base


@dataclass
class GameState:
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
            return None
        player = Player(name=name)
        self.players.append(player)
        return player

    def remove_player(self, name: str) -> None:
        self.players = [p for p in self.players if p.name != name]

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

    def start_game(self) -> None:
        self.phase = GamePhase.PLAYING
        self.round_number = 0
        for p in self.players:
            p.score = 0
        self.available_tracks = list(self.playlist_tracks)
        random.shuffle(self.available_tracks)

    def start_round(self) -> RoundState | None:
        if not self.available_tracks:
            self.available_tracks = list(self.playlist_tracks)
            random.shuffle(self.available_tracks)

        if not self.available_tracks:
            return None

        track = self.available_tracks.pop()
        self.round_number += 1

        order = [p.name for p in self.players]
        random.shuffle(order)

        self.current_round = RoundState(track=track, player_order=order)
        self.phase = GamePhase.PLAYING
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
            return
        pts = compute_points(song_correct, artist_correct, year_correct)
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
                break
        self.current_round.current_player_idx += 1

    def skip_turn(self, player_name: str) -> None:
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

    def is_game_over(self) -> bool:
        if self.total_rounds == 0:
            return False  # endless
        return self.round_number >= self.total_rounds

    def end_game(self) -> None:
        self.phase = GamePhase.FINISHED

    def get_leaderboard(self) -> list[Player]:
        return sorted(self.players, key=lambda p: p.score, reverse=True)

    def reset(self) -> None:
        self.players.clear()
        self.playlist_tracks.clear()
        self.available_tracks.clear()
        self.current_round = None
        self.round_number = 0
        self.total_rounds = 0
        self.phase = GamePhase.LOBBY
        self.device_id = None
        self.year_enrichment_done = False
