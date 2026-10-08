"""Fuzzy-tolerant duplicate detection via normalised fingerprints.

Exact string comparison misses duplicates that differ only in case,
whitespace, punctuation, curly vs straight quotes or accents. Each record is
reduced to a normalised *key* and hashed into a deterministic *fingerprint*:

* books:  ``source | normalised title``
* quotes: ``source | normalised author | first QUOTE_PREFIX_CHARS of normalised quote``
* other:  ``source | normalised name_or_title``

The first record with a given fingerprint is kept; later ones are duplicates.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

from schema import QUOTES_SOURCE

QUOTE_PREFIX_CHARS = 80


def normalize_for_fingerprint(value: Any) -> str:
    """Case-fold, strip accents, replace punctuation/symbols with spaces and
    collapse whitespace: ``"  Héllo,  WORLD!! "`` -> ``"hello world"``."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    chars = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Mn":  # combining accent marks
            continue
        chars.append(" " if category[0] in {"P", "S"} else char)
    return " ".join("".join(chars).casefold().split())


def fingerprint_key(record: dict[str, Any]) -> str:
    source = record.get("source") or ""
    title = normalize_for_fingerprint(record.get("name_or_title"))
    if source == QUOTES_SOURCE:
        author = normalize_for_fingerprint(record.get("author"))
        return f"{source}|{author}|{title[:QUOTE_PREFIX_CHARS]}"
    # Books (and any future source without a better identity) use the title.
    return f"{source}|{title}"


def fingerprint(record: dict[str, Any]) -> str:
    """Stable SHA-256 hex digest of the normalised key."""
    return hashlib.sha256(fingerprint_key(record).encode("utf-8")).hexdigest()


def deduplicate(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (unique, duplicates), preserving input order.

    Each duplicate is a copy annotated with its ``fingerprint`` and
    ``duplicate_of`` (the ``source_url`` of the record that was kept).
    """
    kept_by_fp: dict[str, dict[str, Any]] = {}
    unique: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for record in records:
        fp = fingerprint(record)
        original = kept_by_fp.get(fp)
        if original is None:
            kept_by_fp[fp] = record
            unique.append(record)
        else:
            duplicates.append({**record, "fingerprint": fp, "duplicate_of": original.get("source_url")})
    return unique, duplicates
