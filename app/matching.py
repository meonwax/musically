from __future__ import annotations

import re

from thefuzz import fuzz


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s*\(.*?\)\s*", " ", text)  # remove parenthesised parts
    text = re.sub(r"\s*\[.*?\]\s*", " ", text)  # remove bracketed parts
    text = re.sub(r"[^\w\s]", "", text)  # strip punctuation
    text = re.sub(r"\s+", " ", text).strip()  # collapse whitespace
    return text


def check_guess(guess: str, target: str, threshold: int = 75) -> bool:
    g = normalize(guess)
    t = normalize(target)

    if not g:
        return False

    ratio = fuzz.token_sort_ratio(g, t)
    if ratio >= threshold:
        return True

    if fuzz.partial_ratio(g, t) >= threshold + 10:
        return True

    return False


def check_artist(guess: str, artists: list[str], threshold: int = 75) -> bool:
    """Match the guess against any of the track's artists."""
    if not guess or not guess.strip():
        return False
    for artist in artists:
        if check_guess(guess, artist, threshold):
            return True
    return False


def check_year(guess: int | None, actual: int | None) -> bool:
    if guess is None or actual is None:
        return False
    return guess == actual
