from __future__ import annotations

import asyncio
import logging

import httpx

from app.game import Track
from app.matching import clean_title

logger = logging.getLogger(__name__)

MB_API_BASE = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "Musically/0.1 (https://github.com/musically-game)"
REQUEST_DELAY = 1.0  # MusicBrainz rate-limit: 1 req/s


def _quote(value: str) -> str:
    """Build a Lucene phrase literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


async def lookup_original_year(
    title: str,
    artist: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> int | None:
    """Search MusicBrainz recordings and return the earliest release year found."""
    query = f"recording:{_quote(clean_title(title))} AND artist:{_quote(artist)}"
    params = {"query": query, "fmt": "json", "limit": 100}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    try:
        resp = await client.get(
            f"{MB_API_BASE}/recording",
            params=params,
            headers={"User-Agent": MB_USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("MusicBrainz lookup failed for %r by %r", title, artist)
        return None
    finally:
        if own_client:
            await client.aclose()

    min_year: int | None = None
    for recording in data.get("recordings", []):
        frd = recording.get("first-release-date", "")
        if len(frd) >= 4:
            try:
                year = int(frd[:4])
            except ValueError:
                continue
            if min_year is None or year < min_year:
                min_year = year
    return min_year


async def enrich_tracks(
    tracks: list[Track],
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Update each track's year with the original release year from MusicBrainz.

    Only overwrites the year if MusicBrainz reports an earlier one.
    Sleeps between requests to respect the 1 req/s rate limit.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    try:
        for i, track in enumerate(tracks):
            if i > 0:
                await asyncio.sleep(REQUEST_DELAY)
            primary_artist = track.artists[0] if track.artists else ""
            mb_year = await lookup_original_year(
                track.name, primary_artist, client=client
            )
            if mb_year is not None:
                if track.year is None or mb_year < track.year:
                    logger.info(
                        "Corrected year for %r: %s -> %s",
                        track.name,
                        track.year,
                        mb_year,
                    )
                    track.year = mb_year
    finally:
        if own_client:
            await client.aclose()
