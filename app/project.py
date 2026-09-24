from __future__ import annotations

import tomllib
from dataclasses import dataclass

from app.game_config import PROJECT_ROOT


@dataclass(frozen=True)
class ProjectInfo:
    version: str
    repository: str


def load_project_info() -> ProjectInfo:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        project = tomllib.load(f)["project"]
    return ProjectInfo(
        version=project["version"],
        repository=project["urls"]["Repository"],
    )
