from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.project import load_project_info

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["project"] = load_project_info()
