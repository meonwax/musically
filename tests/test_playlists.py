from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.playlists import PredefinedPlaylist, load_predefined_playlists


class TestLoadPredefinedPlaylists:
    def test_loads_default_config(self):
        playlists = load_predefined_playlists()
        assert len(playlists) >= 1
        assert playlists[0] == PredefinedPlaylist(
            name="Rolling Stone 500 Best Songs Of All Time",
            url="https://open.spotify.com/playlist/7kcvsrztoIt6CvWxpY0tGs?si=cd112b5207b84da3",
        )

    def test_loads_custom_path(self, tmp_path: Path):
        config = tmp_path / "playlists.json"
        config.write_text(
            json.dumps(
                [{"name": "Test Playlist", "url": "https://open.spotify.com/playlist/abc"}]
            ),
            encoding="utf-8",
        )
        playlists = load_predefined_playlists(config)
        assert playlists == [
            PredefinedPlaylist(
                name="Test Playlist",
                url="https://open.spotify.com/playlist/abc",
            )
        ]

    def test_rejects_non_array_root(self, tmp_path: Path):
        config = tmp_path / "playlists.json"
        config.write_text('{"name": "x", "url": "y"}', encoding="utf-8")
        with pytest.raises(ValueError, match="expected a JSON array"):
            load_predefined_playlists(config)

    def test_rejects_missing_fields(self, tmp_path: Path):
        config = tmp_path / "playlists.json"
        config.write_text('[{"name": "Only Name"}]', encoding="utf-8")
        with pytest.raises(ValueError, match="requires 'name' and 'url'"):
            load_predefined_playlists(config)
