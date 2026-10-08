import math

import pytest

from processing.validation import partition_valid, validate_record
from schema import PARSE_ERROR_KEY


def test_valid_book_and_quote_pass(valid_book, valid_quote):
    assert validate_record(valid_book) == []
    assert validate_record(valid_quote) == []


@pytest.mark.parametrize("title", [None, "", "   "])
def test_missing_title(valid_book, title):
    valid_book["name_or_title"] = title
    assert validate_record(valid_book) == ["missing_title"]


def test_missing_schema_field_is_malformed(valid_book):
    del valid_book["category"]
    assert validate_record(valid_book) == ["malformed_record"]


def test_scraper_parse_error_is_malformed(valid_book):
    valid_book[PARSE_ERROR_KEY] = "AttributeError: boom"
    assert validate_record(valid_book) == ["malformed_record"]


@pytest.mark.parametrize("price", [-0.01, "free", math.nan, math.inf, True])
def test_invalid_price(valid_book, price):
    valid_book["price"] = price
    assert validate_record(valid_book) == ["invalid_price"]


def test_zero_price_is_allowed(valid_book):
    valid_book["price"] = 0.0
    assert validate_record(valid_book) == []


def test_book_requires_price_and_rating(valid_book):
    valid_book["price"] = None
    valid_book["rating"] = None
    assert validate_record(valid_book) == ["missing_price", "missing_rating"]


def test_quote_without_price_or_rating_is_fine(valid_quote):
    assert valid_quote["price"] is None and valid_quote["rating"] is None
    assert validate_record(valid_quote) == []


@pytest.mark.parametrize("rating", [0, 6, -1, "Seven", 3.5, True])
def test_invalid_rating(valid_book, rating):
    valid_book["rating"] = rating
    assert validate_record(valid_book) == ["invalid_rating"]


@pytest.mark.parametrize("rating", [1, 5])
def test_rating_bounds_inclusive(valid_book, rating):
    valid_book["rating"] = rating
    assert validate_record(valid_book) == []


@pytest.mark.parametrize("url", [None, "", "not a url", "/catalogue/x.html", "ftp://books.toscrape.com/x", "https://"])
def test_invalid_url(valid_book, url):
    valid_book["source_url"] = url
    assert validate_record(valid_book) == ["invalid_url"]


def test_invalid_author_url(valid_quote):
    valid_quote["author_url"] = "/author/Albert-Einstein"
    assert validate_record(valid_quote) == ["invalid_author_url"]


@pytest.mark.parametrize("source", ["amazon", "", None, "Books_ToScrape"])
def test_unknown_source(valid_quote, source):
    valid_quote["source"] = source
    assert "unknown_source" in validate_record(valid_quote)


def test_quote_requires_author(valid_quote):
    valid_quote["author"] = None
    assert validate_record(valid_quote) == ["missing_author"]


def test_tags_must_be_list_of_strings(valid_quote):
    valid_quote["tags"] = "change|thinking"
    assert validate_record(valid_quote) == ["invalid_tags"]


def test_scraped_at_must_be_iso(valid_quote):
    valid_quote["scraped_at"] = "yesterday"
    assert validate_record(valid_quote) == ["invalid_scraped_at"]


def test_multiple_reasons_are_all_reported(valid_book):
    valid_book.update(source="unknown", name_or_title="", price="abc", rating=9, source_url="nope")
    assert validate_record(valid_book) == [
        "unknown_source", "missing_title", "invalid_url", "invalid_price", "invalid_rating"
    ]


def test_partition_keeps_rejected_records_with_reasons(valid_book, valid_quote):
    bad = {**valid_book, "price": -1.0}
    valid, rejected = partition_valid([valid_book, bad, valid_quote])
    assert valid == [valid_book, valid_quote]
    assert len(rejected) == 1
    assert rejected[0]["rejection_reasons"] == ["invalid_price"]
    assert rejected[0]["name_or_title"] == valid_book["name_or_title"]
