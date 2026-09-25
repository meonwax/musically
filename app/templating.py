from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.game import MAX_PLAYERS, PlayerColor
from app.i18n import LANGUAGES, preferred_language
from app.project import load_project_info

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["project"] = load_project_info()
templates.env.globals["player_colors"] = list(PlayerColor)
templates.env.globals["max_players"] = MAX_PLAYERS
templates.env.globals["languages"] = LANGUAGES
templates.env.globals["preferred_language"] = preferred_language
