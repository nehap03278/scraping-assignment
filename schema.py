"""The common data model shared by every source.

Every record, whatever site it came from, is a dict with exactly these keys.
Fields that a source does not provide stay ``None`` (or an empty tag list);
they are never filled with guessed values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

BOOKS_SOURCE = "books_toscrape"
QUOTES_SOURCE = "quotes_toscrape"
KNOWN_SOURCES = frozenset({BOOKS_SOURCE, QUOTES_SOURCE})

# Deterministic column order of the final dataset.
FIELDNAMES: tuple[str, ...] = (
    "source",         # which site produced the record
    "source_url",     # book detail page / quotes listing page the record came from
    "name_or_title",  # book title, or the quote text for quotes
    "category",       # book genre from the breadcrumb; None for quotes
    "price",          # float in GBP for books; None for quotes
    "rating",         # int 1..5 for books; None for quotes
    "author",         # quote author; None for books (the site does not list one)
    "author_url",     # absolute URL of the quote author's "about" page; None for books
    "tags",           # list[str] of quote tags; [] for books
    "description",    # book product description; None for quotes
    "scraped_at",     # UTC ISO-8601 timestamp of extraction
)

# Internal marker set by a scraper when an item could not be parsed at all.
PARSE_ERROR_KEY = "_parse_error"


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_record(source: str, source_url: str | None) -> dict[str, Any]:
    """A record with every schema field present and nothing invented."""
    record: dict[str, Any] = {field: None for field in FIELDNAMES}
    record["source"] = source
    record["source_url"] = source_url
    record["tags"] = []
    record["scraped_at"] = utc_now_iso()
    return record
