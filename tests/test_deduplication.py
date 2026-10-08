from processing.deduplication import (
    QUOTE_PREFIX_CHARS,
    deduplicate,
    fingerprint,
    fingerprint_key,
    normalize_for_fingerprint,
)


def test_normalisation_ignores_case_whitespace_punctuation_and_accents():
    assert normalize_for_fingerprint("  Héllo,   WORLD!! ") == "hello world"
    assert normalize_for_fingerprint("“Don’t panic.”") == normalize_for_fingerprint('"Don\'t panic"')


def test_fingerprint_is_deterministic(valid_book):
    assert fingerprint(valid_book) == fingerprint(dict(valid_book))
    assert len(fingerprint(valid_book)) == 64


def test_identical_records_are_duplicates(valid_book):
    unique, dups = deduplicate([valid_book, dict(valid_book)])
    assert unique == [valid_book]
    assert len(dups) == 1
    assert dups[0]["duplicate_of"] == valid_book["source_url"]
    assert dups[0]["fingerprint"] == fingerprint(valid_book)


def test_case_difference_is_duplicate(valid_book):
    other = {**valid_book, "name_or_title": "a LIGHT in THE attic"}
    assert len(deduplicate([valid_book, other])[1]) == 1


def test_whitespace_difference_is_duplicate(valid_book):
    other = {**valid_book, "name_or_title": "  A  Light\nin the   Attic "}
    assert len(deduplicate([valid_book, other])[1]) == 1


def test_punctuation_difference_is_duplicate(valid_quote):
    other = {
        **valid_quote,
        "name_or_title": "The world, as we have created it, is a process of our thinking!",
        "author": "albert  einstein.",
    }
    assert len(deduplicate([valid_quote, other])[1]) == 1


def test_book_duplicate_detected_even_if_url_differs(valid_book):
    other = {**valid_book, "source_url": "https://books.toscrape.com/catalogue/copy_1/index.html", "price": 10.0}
    unique, dups = deduplicate([valid_book, other])
    assert unique == [valid_book]
    assert dups[0]["duplicate_of"] == valid_book["source_url"]


def test_distinct_records_are_kept(valid_book, valid_quote):
    other_book = {**valid_book, "name_or_title": "Tipping the Velvet"}
    other_quote = {**valid_quote, "name_or_title": "Imagination is more important than knowledge."}
    unique, dups = deduplicate([valid_book, other_book, valid_quote, other_quote])
    assert len(unique) == 4 and dups == []


def test_same_quote_different_author_is_distinct(valid_quote):
    other = {**valid_quote, "author": "Someone Else"}
    assert deduplicate([valid_quote, other])[1] == []


def test_same_title_in_different_sources_is_distinct(valid_book, valid_quote):
    quote_with_book_title = {**valid_quote, "name_or_title": valid_book["name_or_title"], "author": None}
    assert deduplicate([valid_book, quote_with_book_title])[1] == []


def test_quote_key_uses_only_prefix_of_text(valid_quote):
    base = "x" * QUOTE_PREFIX_CHARS
    a = {**valid_quote, "name_or_title": base + " ending one"}
    b = {**valid_quote, "name_or_title": base + " ending two"}
    assert fingerprint_key(a) == fingerprint_key(b)


def test_first_occurrence_wins_and_order_is_preserved(valid_book):
    titles = ["B", "a", "b", "C", "A"]
    records = [{**valid_book, "name_or_title": t, "source_url": f"https://x.test/{i}"} for i, t in enumerate(titles)]
    unique, dups = deduplicate(records)
    assert [r["name_or_title"] for r in unique] == ["B", "a", "C"]
    assert [d["duplicate_of"] for d in dups] == ["https://x.test/0", "https://x.test/1"]
