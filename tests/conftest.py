"""Shared fixtures: offline HTTP fake and sample records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from schema import BOOKS_SOURCE, QUOTES_SOURCE
from scrapers.http_client import FetchError

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content


class FakeClient:
    """Stands in for HttpClient: serves fixture files by URL, fails otherwise."""

    def __init__(self, pages: dict[str, str | bytes]) -> None:
        self.pages = {
            url: (FIXTURES / body).read_bytes() if isinstance(body, str) else body
            for url, body in pages.items()
        }
        self.requested: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.requested.append(url)
        if url not in self.pages:
            raise FetchError(url, "HTTP 404")
        return FakeResponse(self.pages[url])


@pytest.fixture
def fake_client_factory():
    return FakeClient


@pytest.fixture
def valid_book() -> dict[str, Any]:
    return {
        "source": BOOKS_SOURCE,
        "source_url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "name_or_title": "A Light in the Attic",
        "category": "Poetry",
        "price": 51.77,
        "rating": 3,
        "author": None,
        "author_url": None,
        "tags": [],
        "description": "It's hard to imagine a world without A Light in the Attic.",
        "scraped_at": "2026-10-06T08:45:20+00:00",
    }


@pytest.fixture
def valid_quote() -> dict[str, Any]:
    return {
        "source": QUOTES_SOURCE,
        "source_url": "https://quotes.toscrape.com/",
        "name_or_title": "The world as we have created it is a process of our thinking.",
        "category": None,
        "price": None,
        "rating": None,
        "author": "Albert Einstein",
        "author_url": "https://quotes.toscrape.com/author/Albert-Einstein",
        "tags": ["change", "thinking"],
        "description": None,
        "scraped_at": "2026-10-06T08:45:43+00:00",
    }
