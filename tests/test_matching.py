from __future__ import annotations

import pytest

from app.matching import check_artist, check_guess, check_year, normalize


class TestNormalize:
    def test_lowercase(self):
        assert normalize("HELLO") == "hello"

    def test_strip_whitespace(self):
        assert normalize("  hello  ") == "hello"

    def test_collapse_whitespace(self):
        assert normalize("hello   world") == "hello world"

    def test_strip_punctuation(self):
        assert normalize("hello, world!") == "hello world"

    def test_remove_parenthesised(self):
        assert normalize("Song (feat. Artist)") == "song"

    def test_remove_bracketed(self):
        assert normalize("Song [Remastered]") == "song"

    def test_combined_normalization(self):
        assert normalize("  Don't Stop (Radio Edit) [2011]  ") == "dont stop"

    def test_empty_string(self):
        assert normalize("") == ""

    def test_only_punctuation(self):
        assert normalize("!!!") == ""


class TestCheckGuess:
    def test_exact_match(self):
        assert check_guess("Bohemian Rhapsody", "Bohemian Rhapsody") is True

    def test_case_insensitive(self):
        assert check_guess("bohemian rhapsody", "Bohemian Rhapsody") is True

    def test_word_order_irrelevant(self):
        assert check_guess("Rhapsody Bohemian", "Bohemian Rhapsody") is True

    def test_minor_typo(self):
        assert check_guess("Bohemian Rapsody", "Bohemian Rhapsody") is True

    def test_with_parenthesised_suffix(self):
        assert check_guess("Bohemian Rhapsody", "Bohemian Rhapsody (Remastered)") is True

    def test_completely_wrong(self):
        assert check_guess("Yesterday", "Bohemian Rhapsody") is False

    def test_empty_guess(self):
        assert check_guess("", "Bohemian Rhapsody") is False

    def test_whitespace_guess(self):
        assert check_guess("   ", "Bohemian Rhapsody") is False

    def test_partial_match_short_title(self):
        assert check_guess("Imagine", "Imagine") is True

    def test_partial_match_long_title(self):
        assert check_guess("Smells Like Teen Spirit", "Smells Like Teen Spirit") is True

    def test_close_but_wrong(self):
        assert check_guess("Stairway to Hell", "Stairway to Heaven") is True

    def test_threshold_respected(self):
        assert check_guess("abc", "Bohemian Rhapsody", threshold=99) is False

    def test_very_similar(self):
        assert check_guess("Hotel Calfornia", "Hotel California") is True


class TestCheckArtist:
    def test_exact_artist_match(self):
        assert check_artist("Queen", ["Queen"]) is True

    def test_case_insensitive(self):
        assert check_artist("queen", ["Queen"]) is True

    def test_typo_in_artist(self):
        assert check_artist("Quen", ["Queen"]) is True

    def test_multiple_artists_first(self):
        assert check_artist("Drake", ["Drake", "Rihanna"]) is True

    def test_multiple_artists_second(self):
        assert check_artist("Rihanna", ["Drake", "Rihanna"]) is True

    def test_wrong_artist(self):
        assert check_artist("Beatles", ["Queen"]) is False

    def test_empty_guess(self):
        assert check_artist("", ["Queen"]) is False

    def test_whitespace_guess(self):
        assert check_artist("   ", ["Queen"]) is False

    def test_long_artist_name(self):
        assert check_artist("Led Zeppelin", ["Led Zeppelin"]) is True

    def test_partial_artist_typo(self):
        assert check_artist("Led Zepelin", ["Led Zeppelin"]) is True


class TestCheckYear:
    def test_exact_match(self):
        assert check_year(1975, 1975) is True

    def test_wrong_year(self):
        assert check_year(1976, 1975) is False

    def test_none_guess(self):
        assert check_year(None, 1975) is False

    def test_none_actual(self):
        assert check_year(1975, None) is False

    def test_both_none(self):
        assert check_year(None, None) is False
