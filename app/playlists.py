from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAYLISTS_PATH = PROJECT_ROOT / "config" / "playlists.json"


@dataclass(frozen=True)
class PredefinedPlaylist:
    name: str
    url: str


def load_predefined_playlists(
    path: Path | None = None,
) -> list[PredefinedPlaylist]:
    config_path = path or DEFAULT_PLAYLISTS_PATH
    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{config_path}: expected a JSON array")

    playlists: list[PredefinedPlaylist] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{config_path}: entry {i} must be an object")
        name = item.get("name")
        url = item.get("url")
        if not name or not url:
            raise ValueError(f"{config_path}: entry {i} requires 'name' and 'url'")
        playlists.append(PredefinedPlaylist(name=str(name), url=str(url)))
    return playlists
