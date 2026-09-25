from __future__ import annotations

from fastapi.responses import HTMLResponse


def htmx_redirect(url: str) -> HTMLResponse:
    # A plain redirect would make HTMX swap the whole target page into the partial.
    return HTMLResponse("", headers={"HX-Redirect": url})
