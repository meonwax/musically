from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "musically.toml"


@dataclass(frozen=True)
class PredefinedPlaylist:
    name: str
    url: str


@dataclass(frozen=True)
class ScoringConfig:
    song: int
    artist: int
    year_multiplier: int

    def year_hint(self) -> str:
        if self.year_multiplier == 2:
            return "doubles your points"
        return f"multiplies your points by {self.year_multiplier}"


@dataclass(frozen=True)
class GameConfig:
    playlists: list[PredefinedPlaylist]
    points: ScoringConfig


def _parse_playlists(
    data: dict[str, object], config_path: Path
) -> list[PredefinedPlaylist]:
    playlists: list[PredefinedPlaylist] = []
    for name, url in data.items():
        if not name.strip():
            raise ValueError(f"{config_path}: playlists keys must not be empty")
        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                f"{config_path}: playlists.{name!r} must be a non-empty URL"
            )
        playlists.append(PredefinedPlaylist(name=name, url=url))
    return playlists


def _parse_points(data: dict[str, object], config_path: Path) -> ScoringConfig:
    song = data.get("song", 1)
    artist = data.get("artist", 1)
    year_multiplier = data.get("year_multiplier", 2)
    for field_name, value in (
        ("song", song),
        ("artist", artist),
        ("year_multiplier", year_multiplier),
    ):
        if not isinstance(value, int) or value < 1:
            raise ValueError(
                f"{config_path}: points.{field_name} must be a positive integer"
            )
    return ScoringConfig(
        song=song,
        artist=artist,
        year_multiplier=year_multiplier,
    )


def load_game_config(path: Path | None = None) -> GameConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    playlists_raw = data.get("playlists", {})
    if not isinstance(playlists_raw, dict):
        raise ValueError(f"{config_path}: 'playlists' must be a table")

    points_raw = data.get("points", {})
    if not isinstance(points_raw, dict):
        raise ValueError(f"{config_path}: 'points' must be a table")

    return GameConfig(
        playlists=_parse_playlists(playlists_raw, config_path),
        points=_parse_points(points_raw, config_path),
    )
