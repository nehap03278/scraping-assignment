"""Field-level cleaning functions and the record-level ``clean_record``.

Principle: cleaning *normalises* values but never *invents* them.
* Missing / blank input becomes ``None`` (or ``[]`` for tags).
* A value that cannot be interpreted (e.g. price "free") is returned
  unchanged, so validation can reject it with a precise reason instead of the
  pipeline quietly turning it into a plausible-looking number.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from schema import PARSE_ERROR_KEY

_WHITESPACE = re.compile(r"\s+")
# Zero-width and BOM characters that sometimes leak out of HTML.
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_OPENING_QUOTES = "\"'“‘«„"
_CLOSING_QUOTES = "\"'”’»“"
# Optional currency symbol(s), then a plain decimal number. Letters are not
# allowed, so "abc5" stays invalid instead of quietly becoming 5.0.
_PRICE = re.compile(r"[^\w\s\-+]*\s*([-+]?\d+(?:\.\d+)?)")
# "£" decoded with the wrong charset (UTF-8 bytes read as Latin-1).
_MOJIBAKE_POUND = "Â£"
_RATING_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_TAG_SEPARATORS = re.compile(r"[,;|]")


def normalize_whitespace(value: Any) -> str | None:
    """Unicode-normalise (NFC), drop invisible chars, collapse runs of whitespace.

    Returns ``None`` for ``None`` or strings that are empty after stripping.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFC", str(value)).translate(_INVISIBLE)
    text = _WHITESPACE.sub(" ", text).strip()  # \s also covers \xa0, \n, \t
    return text or None


def strip_wrapping_quotes(value: str | None) -> str | None:
    """Remove one pair of decorative quote marks around a whole string.

    ``“Be yourself.”`` -> ``Be yourself.``; quotes inside the text are kept.
    """
    text = normalize_whitespace(value)
    if text and len(text) >= 2 and text[0] in _OPENING_QUOTES and text[-1] in _CLOSING_QUOTES:
        text = normalize_whitespace(text[1:-1])
    return text


def clean_price(value: Any) -> float | Any:
    """``"£51.77"`` -> ``51.77``.

    Accepts numbers or strings with a currency symbol/thousands separators.
    Missing -> ``None``; uninterpretable -> original value (validation rejects
    it). Negative numbers are parsed, not "fixed"; validation rejects them.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 2) if math.isfinite(value) else value
    text = normalize_whitespace(value)
    if text is None:
        return None
    match = _PRICE.fullmatch(text.replace(_MOJIBAKE_POUND, "£").replace(",", ""))
    return round(float(match.group(1)), 2) if match else text


def clean_rating(value: Any) -> int | Any:
    """``"Three"`` / ``"3"`` / ``3`` -> ``3``.

    Missing -> ``None``; uninterpretable -> original value. The 1..5 range is a
    validation rule, so ``"Seven"``-style input is not clamped here.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = normalize_whitespace(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in _RATING_WORDS:
        return _RATING_WORDS[lowered]
    if re.fullmatch(r"[-+]?\d+", lowered):
        return int(lowered)
    return text


def clean_tags(value: Any) -> list[str]:
    """Lower-case, trim and de-duplicate tags, keeping first-seen order.

    Accepts a list or a single string separated by ``,`` ``;`` or ``|``.
    """
    if value is None:
        return []
    raw = _TAG_SEPARATORS.split(value) if isinstance(value, str) else list(value)
    tags: list[str] = []
    for tag in raw:
        cleaned = normalize_whitespace(tag)
        if cleaned:
            cleaned = cleaned.lower()
            if cleaned not in tags:
                tags.append(cleaned)
    return tags


def clean_url(value: Any, base_url: str | None = None) -> str | None:
    """Trim, resolve relative URLs against ``base_url``, lower-case scheme and
    host, and drop the ``#fragment``. Validity is checked in validation."""
    text = normalize_whitespace(value)
    if text is None:
        return None
    if base_url:
        text = urljoin(base_url, text)
    parts = urlsplit(text)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def clean_description(value: Any) -> str | None:
    """Normalise whitespace and drop the site's trailing "...more" UI marker.

    Books to Scrape descriptions end with the literal text ``...more`` (a
    "read more" affordance, not part of the description). The text before it
    is kept exactly as published.
    """
    text = normalize_whitespace(value)
    if text and text.endswith("...more"):
        text = normalize_whitespace(text[: -len("...more")])
    return text


def clean_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a new record with every schema field cleaned.

    Unknown keys are dropped except the internal parse-error marker, which is
    carried through so validation can report the record as malformed.
    """
    source_url = clean_url(raw.get("source_url"))
    record: dict[str, Any] = {
        "source": normalize_whitespace(raw.get("source")),
        "source_url": source_url,
        "name_or_title": strip_wrapping_quotes(raw.get("name_or_title")),
        "category": normalize_whitespace(raw.get("category")),
        "price": clean_price(raw.get("price")),
        "rating": clean_rating(raw.get("rating")),
        "author": normalize_whitespace(raw.get("author")),
        "author_url": clean_url(raw.get("author_url"), base_url=source_url),
        "tags": clean_tags(raw.get("tags")),
        "description": clean_description(raw.get("description")),
        "scraped_at": normalize_whitespace(raw.get("scraped_at")),
    }
    if raw.get(PARSE_ERROR_KEY):
        record[PARSE_ERROR_KEY] = raw[PARSE_ERROR_KEY]
    return record
