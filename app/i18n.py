from __future__ import annotations

LANGUAGES: dict[str, str] = {"en": "English", "de": "Deutsch"}
DEFAULT_LANGUAGE = "en"


def preferred_language(accept_language: str) -> str:
    """The supported language an Accept-Language header ranks highest."""
    best, best_q = DEFAULT_LANGUAGE, 0.0
    for item in accept_language.split(","):
        tag, _, params = item.partition(";")
        code = tag.strip().split("-")[0].lower()
        q = 1.0
        for param in params.split(";"):
            key, _, value = param.partition("=")
            if key.strip() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        # Strictly greater, so the earlier of equally ranked languages wins.
        if code in LANGUAGES and q > best_q:
            best, best_q = code, q
    return best
