from __future__ import annotations

import pytest

from app.matching import check_artist, check_guess, check_year, clean_title, normalize


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

    def test_strips_spotify_version_suffix(self):
        assert normalize("Help! - Remastered 2009") == "help"

    def test_strips_leading_the(self):
        assert normalize("The Beatles") == "beatles"

    def test_keeps_lone_the(self):
        assert normalize("The") == "the"


class TestCleanTitle:
    def test_version_suffix(self):
        assert clean_title("Bohemian Rhapsody - Remastered 2011") == "Bohemian Rhapsody"

    def test_bracketed_parts(self):
        assert clean_title("Song (feat. Artist) [Live]") == "Song"

    def test_keeps_case_and_punctuation(self):
        assert clean_title("Don't Stop Me Now - 2011 Mix") == "Don't Stop Me Now"

    def test_hyphen_without_spaces_is_kept(self):
        assert clean_title("Anti-Hero") == "Anti-Hero"


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

    @pytest.mark.parametrize(
        "guess,target",
        [
            ("love", "Crazy Little Thing Called Love"),
            ("heaven", "Stairway to Heaven"),
            ("a", "A Hard Day's Night"),
            ("jude", "Hey Jude"),
        ],
    )
    def test_single_word_from_title_is_not_enough(self, guess: str, target: str):
        assert check_guess(guess, target) is False

    def test_ignores_spotify_version_suffix(self):
        assert check_guess("Bohemian Rhapsody", "Bohemian Rhapsody - Remastered 2011") is True

    def test_leading_bracket_optional(self):
        target = "(I Can't Get No) Satisfaction - Mono Version"
        assert check_guess("Satisfaction", target) is True
        assert check_guess("I can't get no satisfaction", target) is True


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

    def test_leading_the_optional(self):
        assert check_artist("Who", ["The Who"]) is True

    def test_lone_the_does_not_match(self):
        assert check_artist("the", ["The Rolling Stones"]) is False


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
