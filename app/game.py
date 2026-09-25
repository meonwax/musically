from __future__ import annotations

import logging
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum, StrEnum, auto

from app.game_config import ScoringConfig
from app.matching import check_artist, check_guess, check_year, display_title

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    LOBBY = auto()
    PLAYING = auto()
    ROUND_RESULT = auto()
    FINISHED = auto()


class PlayerColor(StrEnum):
    """uchū hues a player's turn is themed in. Purple is the app's own color."""

    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    PINK = "pink"


# One color per player, so turns are always told apart.
MAX_PLAYERS = len(PlayerColor)


@dataclass
class Player:
    name: str
    color: PlayerColor = PlayerColor.RED
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
    year_verified: bool = False

    @property
    def display_name(self) -> str:
        return display_title(self.name)


@dataclass(frozen=True)
class Playlist:
    """The Spotify playlist a game draws its tracks from."""

    id: str
    name: str

    @property
    def url(self) -> str:
        return f"https://open.spotify.com/playlist/{self.id}"


@dataclass(frozen=True)
class PlaybackDevice:
    """A Spotify Connect device the game plays on instead of the browser."""

    id: str
    name: str
    type: str


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

    playlist: Playlist | None = None
    playlist_tracks: list[Track] = field(default_factory=list)
    available_tracks: list[Track] = field(default_factory=list)

    current_round: RoundState | None = None
    round_number: int = 0

    year_enrichment_done: bool = False

    # None plays in the browser via the Web Playback SDK. Kept across resets,
    # since it is the host's setup rather than part of a game.
    playback_device: PlaybackDevice | None = None

    @property
    def is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS

    @property
    def turn_color(self) -> PlayerColor | None:
        rnd = self.current_round
        if rnd is None or rnd.current_player is None:
            return None
        player = self._find_player(rnd.current_player)
        return player.color if player else None

    def free_colors(self) -> list[PlayerColor]:
        taken = {p.color for p in self.players}
        return [c for c in PlayerColor if c not in taken]

    def add_player(self, name: str) -> Player | None:
        if self.is_full:
            logger.info("Rejected player %r: game is full", name)
            return None
        if self._find_player(name):
            logger.info("Rejected duplicate player name: %r", name)
            return None
        player = Player(name=name, color=self.free_colors()[0])
        self.players.append(player)
        logger.info(
            "Player added: %r color=%s (%d total)", name, player.color, len(self.players)
        )
        return player

    def set_player_color(self, name: str, color: PlayerColor) -> bool:
        """Change a player's color. False if another player already has it."""
        player = self._find_player(name)
        if player is None:
            logger.info("Color change ignored, player not found: %r", name)
            return True
        if player.color != color and color not in self.free_colors():
            logger.info("Rejected color %s for %r: taken", color, name)
            return False
        player.color = color
        logger.info("Player %r color=%s", name, color)
        return True

    def _find_player(self, name: str) -> Player | None:
        return next((p for p in self.players if p.name == name), None)

    def remove_player(self, name: str) -> None:
        if not any(p.name == name for p in self.players):
            logger.info("Remove player ignored, not found: %r", name)
            return
        self.players = [p for p in self.players if p.name != name]
        logger.info("Player removed: %r (%d remaining)", name, len(self.players))

    def set_playlist(
        self, tracks: list[Track], playlist: Playlist | None = None
    ) -> None:
        self.playlist = playlist
        self.playlist_tracks = list(tracks)
        self.available_tracks = []
        self.year_enrichment_done = False
        logger.info(
            "Playlist set: %r, %d tracks",
            playlist.name if playlist else None,
            len(self.playlist_tracks),
        )

    def tracks_to_verify(self) -> Iterator[Track]:
        """Yield tracks whose year isn't verified yet, the current round first.

        The order is re-evaluated on every step, so a game started mid-way
        through the lookup gets its upcoming tracks verified before the rest.
        """
        while True:
            current = [self.current_round.track] if self.current_round else []
            # Rounds pop from the end of available_tracks.
            candidates = [
                *current,
                *reversed(self.available_tracks),
                *self.playlist_tracks,
            ]
            track = next((t for t in candidates if not t.year_verified), None)
            if track is None:
                return
            yield track

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

    def submit_guess(
        self, song: str, artist: str, year: int | None
    ) -> RoundGuess | None:
        """Score the current player's guess and advance to the next player."""
        rnd = self.current_round
        if rnd is None or rnd.current_player is None:
            logger.warning("Ignored guess: no player on turn")
            return None
        song_correct = check_guess(song, rnd.track.name)
        artist_correct = check_artist(artist, rnd.track.artists)
        year_correct = check_year(year, rnd.track.year)
        guess = self._record(
            rnd,
            RoundGuess(
                player_name=rnd.current_player,
                song_guess=song,
                artist_guess=artist,
                year_guess=year,
                song_correct=song_correct,
                artist_correct=artist_correct,
                year_correct=year_correct,
                points=compute_points(
                    song_correct, artist_correct, year_correct, self.scoring
                ),
            ),
        )
        logger.info(
            "Guess recorded: round=%d player=%r points=%d "
            "song=%s artist=%s year=%s",
            self.round_number,
            guess.player_name,
            guess.points,
            song_correct,
            artist_correct,
            year_correct,
        )
        return guess

    def skip_turn(self) -> RoundGuess | None:
        rnd = self.current_round
        if rnd is None or rnd.current_player is None:
            logger.warning("Ignored skip: no player on turn")
            return None
        logger.info(
            "Turn skipped: round=%d player=%r", self.round_number, rnd.current_player
        )
        return self._record(
            rnd,
            RoundGuess(
                player_name=rnd.current_player,
                song_guess="(skipped)",
                artist_guess="",
                year_guess=None,
                song_correct=False,
                artist_correct=False,
                year_correct=False,
                points=0,
            ),
        )

    def _record(self, rnd: RoundState, guess: RoundGuess) -> RoundGuess:
        rnd.guesses.append(guess)
        player = self._find_player(guess.player_name)
        if player:
            player.score += guess.points
            if guess.song_correct:
                player.correct_songs += 1
            if guess.artist_correct:
                player.correct_artists += 1
            if guess.year_correct:
                player.correct_years += 1
        rnd.current_player_idx += 1
        if rnd.all_guessed:
            self.phase = GamePhase.ROUND_RESULT
            logger.info(
                "Round %d finished: answer=%r by %s",
                self.round_number,
                rnd.track.name,
                ", ".join(rnd.track.artists),
            )
        return guess

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
        self.playlist = None
        self.playlist_tracks.clear()
        self.available_tracks.clear()
        self.current_round = None
        self.round_number = 0
        self.total_rounds = 0
        self.phase = GamePhase.LOBBY
        self.year_enrichment_done = False
