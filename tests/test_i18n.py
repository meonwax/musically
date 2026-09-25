from __future__ import annotations

import pytest

from app.i18n import preferred_language


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("en-US,en;q=0.9,de;q=0.8", "en"),
        ("DE", "de"),
        ("fr-FR,fr;q=0.9,de;q=0.7,en;q=0.5", "de"),
        ("en;q=0.5, de;q=0.8", "de"),
        ("de;q=0.8,en;q=0.8", "de"),
        ("fr-FR,fr;q=0.9", "en"),
        ("de;q=0, en;q=0.1", "en"),
        ("de;q=0", "en"),
        ("*", "en"),
        ("de;q=abc,en;q=0.2", "en"),
        ("", "en"),
    ],
)
def test_preferred_language(header: str, expected: str):
    assert preferred_language(header) == expected
