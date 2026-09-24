from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.game import Track
from app.musicbrainz import enrich_tracks, lookup_original_year
from app.project import load_project_info


def _mb_response(recordings: list[dict]) -> httpx.Response:
    """Build a fake MusicBrainz JSON response."""
    return httpx.Response(
        200,
        json={"recordings": recordings},
        request=httpx.Request("GET", "https://musicbrainz.org/ws/2/recording"),
    )


def _recording(first_release_date: str) -> dict:
    return {"first-release-date": first_release_date, "title": "Test"}


class TestLookupOriginalYear:
    async def test_returns_minimum_year(self):
        resp = _mb_response([
            _recording("1998"),
            _recording("1991"),
            _recording("1976"),
            _recording("1970"),
        ])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year("Test", "Artist", client=mock_client)
        assert year == 1970

    async def test_in_the_summertime_mungo_jerry(self):
        """Real-world case: Spotify reports 2000, original is 1970."""
        resp = _mb_response([
            _recording("1998"),
            _recording("1991"),
            _recording("1976"),
            _recording("1993"),
            _recording("2011"),
            _recording("2000"),
            _recording("1970"),
        ])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year(
            "In the Summertime", "Mungo Jerry", client=mock_client
        )
        assert year == 1970

    async def test_handles_full_dates(self):
        resp = _mb_response([
            _recording("2005-03-15"),
            _recording("1982-11-01"),
        ])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year("Song", "Artist", client=mock_client)
        assert year == 1982

    async def test_returns_none_on_empty_results(self):
        resp = _mb_response([])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year("Unknown", "Nobody", client=mock_client)
        assert year is None

    async def test_returns_none_on_network_error(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))

        year = await lookup_original_year("Song", "Artist", client=mock_client)
        assert year is None

    async def test_skips_invalid_dates(self):
        resp = _mb_response([
            _recording(""),
            _recording("????"),
            _recording("1985"),
        ])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year("Song", "Artist", client=mock_client)
        assert year == 1985

    async def test_query_uses_clean_title(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=_mb_response([]))

        await lookup_original_year(
            "Bohemian Rhapsody - Remastered 2011", "Queen", client=mock_client
        )
        query = mock_client.get.call_args.kwargs["params"]["query"]
        assert query == 'recording:"Bohemian Rhapsody" AND artist:"Queen"'

    async def test_user_agent_identifies_app(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=_mb_response([]))

        await lookup_original_year("Song", "Artist", client=mock_client)
        project = load_project_info()
        user_agent = mock_client.get.call_args.kwargs["headers"]["User-Agent"]
        assert user_agent == f"Musically/{project.version} ( {project.repository} )"

    async def test_query_escapes_quotes(self):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=_mb_response([]))

        await lookup_original_year('Say "Hi"', "Artist", client=mock_client)
        query = mock_client.get.call_args.kwargs["params"]["query"]
        assert query == 'recording:"Say \\"Hi\\"" AND artist:"Artist"'

    async def test_returns_none_when_all_dates_invalid(self):
        resp = _mb_response([
            _recording(""),
            _recording("N/A"),
        ])
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp)

        year = await lookup_original_year("Song", "Artist", client=mock_client)
        assert year is None


class TestEnrichTracks:
    async def test_updates_year_when_earlier(self):
        tracks = [
            Track(uri="u:1", name="In the Summertime", artists=["Mungo Jerry"], year=2000),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=1970,
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year == 1970

    async def test_keeps_spotify_year_when_mb_later(self):
        tracks = [
            Track(uri="u:1", name="Song", artists=["Artist"], year=1975),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=1998,
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year == 1975

    async def test_keeps_year_when_mb_returns_none(self):
        tracks = [
            Track(uri="u:1", name="Song", artists=["Artist"], year=2000),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year == 2000

    async def test_sets_year_when_spotify_has_none(self):
        tracks = [
            Track(uri="u:1", name="Song", artists=["Artist"], year=None),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=1985,
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year == 1985

    @patch("app.musicbrainz.REQUEST_DELAY", 0)
    async def test_enriches_multiple_tracks(self):
        tracks = [
            Track(uri="u:1", name="Song A", artists=["A"], year=2000),
            Track(uri="u:2", name="Song B", artists=["B"], year=1999),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            side_effect=[1980, 1990],
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year == 1980
        assert tracks[1].year == 1990

    async def test_marks_tracks_verified(self):
        tracks = [Track(uri="u:1", name="Song", artists=["Artist"], year=2000)]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await enrich_tracks(tracks)
        assert tracks[0].year_verified is True

    @patch("app.musicbrainz.REQUEST_DELAY", 0)
    async def test_follows_order_that_changes_during_run(self):
        a = Track(uri="u:1", name="A", artists=["X"], year=2000)
        b = Track(uri="u:2", name="B", artists=["X"], year=2000)
        c = Track(uri="u:3", name="C", artists=["X"], year=2000)
        order = [a, b, c]

        def pending():
            while track := next((t for t in order if not t.year_verified), None):
                yield track

        looked_up = []

        async def fake_lookup(title, artist, *, client):
            looked_up.append(title)
            if title == "A":
                order[:] = [a, c, b]
            return None

        with patch("app.musicbrainz.lookup_original_year", side_effect=fake_lookup):
            await enrich_tracks(pending())
        assert looked_up == ["A", "C", "B"]

    async def test_uses_first_artist(self):
        tracks = [
            Track(uri="u:1", name="Song", artists=["Main", "Feat"], year=2000),
        ]
        with patch(
            "app.musicbrainz.lookup_original_year",
            new_callable=AsyncMock,
            return_value=1990,
        ) as mock_lookup:
            await enrich_tracks(tracks)
        mock_lookup.assert_called_once()
        call_args = mock_lookup.call_args
        assert call_args.args[1] == "Main" or call_args.kwargs.get("artist") == "Main"
