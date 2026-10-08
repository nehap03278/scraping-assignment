import pytest

from processing.cleaning import (
    clean_description,
    clean_price,
    clean_rating,
    clean_record,
    clean_tags,
    clean_url,
    normalize_whitespace,
    strip_wrapping_quotes,
)
from schema import FIELDNAMES, PARSE_ERROR_KEY


class TestWhitespace:
    def test_collapses_internal_and_trims_outer_whitespace(self):
        assert normalize_whitespace("  A   Light\n\tin the\xa0Attic  ") == "A Light in the Attic"

    def test_removes_zero_width_characters(self):
        assert normalize_whitespace("Sharp​ Objects﻿") == "Sharp Objects"

    def test_unicode_is_nfc_normalised(self):
        decomposed = "Café"  # "e" + combining acute accent
        assert normalize_whitespace(decomposed) == "Café"

    @pytest.mark.parametrize("value", [None, "", "   ", "\n\t\xa0"])
    def test_blank_becomes_none(self, value):
        assert normalize_whitespace(value) is None


class TestQuoteMarks:
    def test_strips_curly_wrapping_quotes(self):
        assert strip_wrapping_quotes("“Be yourself.”") == "Be yourself."

    def test_keeps_inner_quotes(self):
        assert strip_wrapping_quotes("He said “hi” today") == "He said “hi” today"

    def test_unquoted_text_unchanged(self):
        assert strip_wrapping_quotes("  plain  text ") == "plain text"


class TestPrice:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("£51.77", 51.77), ("Â£51.77", 51.77), (" £ 1,234.50 ", 1234.5), ("10", 10.0), (12, 12.0), (3.456, 3.46)],
    )
    def test_converts_to_float(self, raw, expected):
        assert clean_price(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_missing_is_none(self, raw):
        assert clean_price(raw) is None

    def test_negative_is_parsed_not_fixed(self):
        assert clean_price("-5.00") == -5.0

    @pytest.mark.parametrize("raw", ["free", "£abc", "1.2.3", "abc5"])
    def test_unparseable_is_returned_for_validation(self, raw):
        assert clean_price(raw) == raw

    def test_bool_is_not_treated_as_number(self):
        assert clean_price(True) is True


class TestRating:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("One", 1), ("three", 3), (" FIVE ", 5), ("4", 4), (2, 2), (4.0, 4)],
    )
    def test_normalises_to_int(self, raw, expected):
        assert clean_rating(raw) == expected

    @pytest.mark.parametrize("raw", [None, ""])
    def test_missing_is_none(self, raw):
        assert clean_rating(raw) is None

    def test_out_of_range_is_not_clamped(self):
        assert clean_rating("9") == 9

    def test_unknown_word_is_returned_for_validation(self):
        assert clean_rating("Seven") == "Seven"


class TestTags:
    def test_lowercases_trims_and_dedupes_in_order(self):
        assert clean_tags([" Life ", "love", "LIFE", "", "  "]) == ["life", "love"]

    def test_accepts_delimited_string(self):
        assert clean_tags("humor; Books|change, ") == ["humor", "books", "change"]

    def test_missing_is_empty_list(self):
        assert clean_tags(None) == []


class TestUrlAndDescription:
    def test_resolves_relative_url_and_drops_fragment(self):
        assert clean_url("/author/Albert-Einstein#bio", "https://quotes.toscrape.com/page/2/") == (
            "https://quotes.toscrape.com/author/Albert-Einstein"
        )

    def test_lowercases_scheme_and_host_only(self):
        assert clean_url(" HTTPS://Books.ToScrape.com/Catalogue/X.html ") == "https://books.toscrape.com/Catalogue/X.html"

    def test_missing_url_is_none(self):
        assert clean_url("  ") is None

    def test_description_drops_more_marker(self):
        assert clean_description("Great   book. ...more") == "Great book."


class TestCleanRecord:
    def test_output_has_schema_fields_in_order(self, valid_quote):
        assert tuple(clean_record(valid_quote)) == FIELDNAMES

    def test_missing_fields_stay_empty_not_invented(self):
        cleaned = clean_record({"source": "quotes_toscrape", "name_or_title": "“Hi”"})
        assert cleaned["name_or_title"] == "Hi"
        assert cleaned["price"] is None
        assert cleaned["rating"] is None
        assert cleaned["category"] is None
        assert cleaned["description"] is None
        assert cleaned["author"] is None
        assert cleaned["tags"] == []

    def test_parse_error_marker_is_kept(self):
        cleaned = clean_record({"source": "books_toscrape", PARSE_ERROR_KEY: "ValueError: boom"})
        assert cleaned[PARSE_ERROR_KEY] == "ValueError: boom"
