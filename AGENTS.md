# Musically - Agent Rules

## Project Overview

Musically is a party-mode song guessing game powered by Spotify.
See `docs/architecture.md` for the full architecture and design plan.

## Tech Stack

- **Backend**: Python 3.12+ / FastAPI
- **Frontend**: HTML + HTMX, minimal vanilla JS for Spotify playback only
- **Package manager**: uv
- **Templates**: Jinja2 (in `app/templates/`)
- **No database**: All state is in-memory via Python dataclasses

## Conventions

- Use `uv add <package>` to add dependencies.
- Run the dev server with `uv run uvicorn app.main:app --reload`.
- Keep JavaScript to the absolute minimum required for playback control (Web Playback SDK and Spotify Connect). All UI interactions should go through HTMX and server-side templates.
- HTMX partials live in `app/templates/partials/` and are returned by routes for partial page updates.
- Full-page templates extend `base.html`.
- Game state lives in `app/game.py` as dataclasses. There is no database.
- Spotify API interaction is encapsulated in `app/spotify.py`.
- Routes render through the shared `templates` instance in `app/templating.py`.
- Configuration is loaded from environment variables via `app/config.py` and `.env`.
- Do not commit `.env` or secrets. Use `.env.example` as the template.

## Versioning

- The version in `pyproject.toml` is shown in the page footer and appended to static file URLs (`?v=`) so browsers fetch changed CSS and JS. Bump it in every commit that changes the app (code, templates, static files, `config.toml`, `Dockerfile`), not for commits that only touch docs or tests.
- Bump with `uv version --bump minor` for new features and `uv version --bump patch` for fixes and small tweaks. This updates `pyproject.toml` and `uv.lock` together; commit both.

## Code Style

- Use `from __future__ import annotations` in all Python files.
- Prefer dataclasses over dicts for structured data.
- Use type hints throughout.
- Keep route handlers thin; business logic belongs in `app/game.py` or `app/matching.py`.
- No CSS frameworks. Keep styling minimal.
- Styling builds on `static/css/monospace.css` (a trimmed copy of The Monospace Web). Keep that file close to upstream and put overrides in `theme.css`, `app.css` or page stylesheets.
- Never hardcode colors. Use the theme variables from `static/css/theme.css` (`--text-color`, `--background-color`, `--color-accent`, ...) so the page follows the player on turn.

## Testing

- Run tests with `uv run pytest` (config in `pyproject.toml`).
- Tests live in `tests/` and mirror the `app/` structure:
  - `test_game.py`: unit tests for game state and logic
  - `test_game_config.py`: unit tests for loading `config.toml`
  - `test_matching.py`: unit tests for fuzzy matching
  - `test_musicbrainz.py`: unit tests for the release year lookup (HTTP mocked)
  - `test_spotify.py`: unit tests for Spotify client (playlist parsing, tokens, auth URL)
  - `test_routes.py`: integration tests for all HTTP routes using FastAPI TestClient
- Shared fixtures are in `tests/conftest.py` (game states, settings, mock Spotify tokens).
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- When changing source code, always update or extend the corresponding tests and run the full suite before considering the task done.
- Use `TemplateResponse(request, "name.html", context={...})` (Starlette 1.0 API). Do NOT pass `request` inside the context dict.

## File Layout

```
app/              Python backend (FastAPI)
app/routes/       Route handlers grouped by feature
app/templates/    Jinja2 full-page templates
app/templates/partials/  HTMX partial templates
static/js/        Client-side JavaScript (Spotify SDK only)
tests/            Pytest test suite
docs/             Architecture and design documentation
```
