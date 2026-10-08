"""Record validation with explicit, countable rejection reasons.

``validate_record`` returns a list of reason codes (empty = valid). A record can
fail for several reasons at once; all of them are reported.

Reason codes
------------
malformed_record   scraper could not parse the item, or schema fields are missing
unknown_source     ``source`` is not one of the known sources
missing_title      ``name_or_title`` is empty
invalid_url        ``source_url`` is not an absolute http(s) URL
invalid_author_url ``author_url`` is present but not an absolute http(s) URL
missing_price      a book has no price
invalid_price      price is not a finite, non-negative number
missing_rating     a book has no rating
invalid_rating     rating is not an integer from 1 to 5
missing_author     a quote has no author
invalid_tags       tags is not a list of strings
invalid_scraped_at scraped_at is not an ISO-8601 timestamp
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from schema import BOOKS_SOURCE, FIELDNAMES, KNOWN_SOURCES, PARSE_ERROR_KEY, QUOTES_SOURCE

MIN_RATING, MAX_RATING = 1, 5


def is_valid_url(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc) and " " not in value


def is_valid_price(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def is_valid_rating(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_RATING <= value <= MAX_RATING


def is_iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_record(record: dict[str, Any]) -> list[str]:
    """Return the list of rejection reasons for ``record`` (empty if valid)."""
    if not isinstance(record, dict) or record.get(PARSE_ERROR_KEY):
        return ["malformed_record"]
    if any(field not in record for field in FIELDNAMES):
        return ["malformed_record"]

    reasons: list[str] = []
    source = record["source"]
    if source not in KNOWN_SOURCES:
        reasons.append("unknown_source")

    title = record["name_or_title"]
    if not isinstance(title, str) or not title.strip():
        reasons.append("missing_title")

    if not is_valid_url(record["source_url"]):
        reasons.append("invalid_url")
    if record["author_url"] is not None and not is_valid_url(record["author_url"]):
        reasons.append("invalid_author_url")

    price = record["price"]
    if price is None:
        if source == BOOKS_SOURCE:
            reasons.append("missing_price")
    elif not is_valid_price(price):
        reasons.append("invalid_price")

    rating = record["rating"]
    if rating is None:
        if source == BOOKS_SOURCE:
            reasons.append("missing_rating")
    elif not is_valid_rating(rating):
        reasons.append("invalid_rating")

    if source == QUOTES_SOURCE and not record["author"]:
        reasons.append("missing_author")

    tags = record["tags"]
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        reasons.append("invalid_tags")

    if not is_iso_timestamp(record["scraped_at"]):
        reasons.append("invalid_scraped_at")

    return reasons


def partition_valid(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split records into (valid, rejected).

    Rejected records are copies annotated with ``rejection_reasons`` so they
    can be written to a report rather than silently dropped.
    """
    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for record in records:
        reasons = validate_record(record)
        if reasons:
            rejected.append({**record, "rejection_reasons": reasons})
        else:
            valid.append(record)
    return valid, rejected
