from __future__ import annotations

import re

from thefuzz import fuzz

# Spotify appends version info after " - ", e.g. "Help! - Remastered 2009".
_VERSION_SUFFIX = re.compile(r"\s+-\s+.*$")
_BRACKETED = re.compile(r"\(.*?\)|\[.*?\]")
_BRACKETED_VERSION = re.compile(
    r"\s*[(\[][^)\]]*\b(?:remaster\w*|version|edit|mono|stereo|mix)\b[^)\]]*[)\]]",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Strip version suffixes and bracketed parts like "(feat. X)" from a title."""
    title = _VERSION_SUFFIX.sub("", title)
    title = _BRACKETED.sub(" ", title)
    return re.sub(r"\s+", " ", title).strip()


def display_title(title: str) -> str:
    """Strip version info like " - Remastered 2012" but keep the rest of the title."""
    stripped = _BRACKETED_VERSION.sub("", _VERSION_SUFFIX.sub("", title))
    return re.sub(r"\s+", " ", stripped).strip() or title


def _simplify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^the ", "", text)


def normalize(text: str) -> str:
    return _simplify(clean_title(text))


def _target_variants(target: str) -> set[str]:
    # Titles like "(I Can't Get No) Satisfaction" should match with or
    # without the bracketed part.
    return {normalize(target), _simplify(_VERSION_SUFFIX.sub("", target))}


def check_guess(guess: str, target: str, threshold: int = 75) -> bool:
    g = normalize(guess)
    if not g:
        return False
    return any(
        fuzz.token_sort_ratio(g, t) >= threshold for t in _target_variants(target)
    )


def check_artist(guess: str, artists: list[str], threshold: int = 75) -> bool:
    """Match the guess against any of the track's artists."""
    return any(check_guess(guess, artist, threshold) for artist in artists)


def check_year(guess: int | None, actual: int | None) -> bool:
    if guess is None or actual is None:
        return False
    return guess == actual
