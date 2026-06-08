from __future__ import annotations

from pathlib import Path

import pytest

from app.game_config import (
    GameConfig,
    PredefinedPlaylist,
    ScoringConfig,
    load_game_config,
)


class TestLoadGameConfig:
    def test_loads_default_config(self):
        config = load_game_config()
        assert len(config.playlists) >= 1
        assert config.playlists[0] == PredefinedPlaylist(
            name="Rolling Stone 500 Best Songs Of All Time",
            url="https://open.spotify.com/playlist/7kcvsrztoIt6CvWxpY0tGs?si=cd112b5207b84da3",
        )
        assert config.points == ScoringConfig(song=1, artist=1, year_multiplier=2)

    def test_loads_custom_path(self, tmp_path: Path):
        config = tmp_path / "config.toml"
        config.write_text(
            """
[playlists]
"Test Playlist" = "https://open.spotify.com/playlist/abc"

[points]
song = 2
artist = 3
year_multiplier = 4
""".strip(),
            encoding="utf-8",
        )
        loaded = load_game_config(config)
        assert loaded == GameConfig(
            playlists=[
                PredefinedPlaylist(
                    name="Test Playlist",
                    url="https://open.spotify.com/playlist/abc",
                )
            ],
            points=ScoringConfig(song=2, artist=3, year_multiplier=4),
        )

    def test_rejects_invalid_playlists_type(self, tmp_path: Path):
        config = tmp_path / "config.toml"
        config.write_text('playlists = "nope"', encoding="utf-8")
        with pytest.raises(ValueError, match="'playlists' must be a table"):
            load_game_config(config)

    def test_rejects_empty_playlist_url(self, tmp_path: Path):
        config = tmp_path / "config.toml"
        config.write_text(
            '[playlists]\n"My Playlist" = ""\n\n[points]\nsong = 1\nartist = 1\nyear_multiplier = 2',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be a non-empty URL"):
            load_game_config(config)

    def test_rejects_invalid_points(self, tmp_path: Path):
        config = tmp_path / "config.toml"
        config.write_text("[points]\nsong = 0", encoding="utf-8")
        with pytest.raises(ValueError, match="points.song must be a positive integer"):
            load_game_config(config)
