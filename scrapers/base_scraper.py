"""Shared crawling logic: pagination, per-item isolation and per-source stats."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from schema import PARSE_ERROR_KEY, empty_record
from scrapers.http_client import FetchError, HttpClient

# Errors a parser can legitimately hit on unexpected markup. Anything else is a
# programming bug and is allowed to propagate.
PARSE_ERRORS = (AttributeError, KeyError, IndexError, TypeError, ValueError)


@dataclass
class ScrapeStats:
    """Measurable facts about one source's crawl, reported in the summary."""

    pages_scraped: int = 0
    pages_failed: int = 0
    next_links_followed: int = 0
    items_found: int = 0
    malformed_items: int = 0
    first_page_url: str | None = None
    last_page_url: str | None = None
    stop_reason: str | None = None
    failed_urls: list[str] = field(default_factory=list)
    extra: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {k: v for k, v in self.__dict__.items() if k != "extra"}
        data.update(self.extra)
        return data


class BaseScraper(ABC):
    """Template for a paginated listing scraper.

    Subclasses only describe *what* to extract (``item_selector`` and
    :meth:`parse_item`); this class owns *how* to crawl: fetching, following
    the ``li.next > a`` link until it disappears, and isolating failures so a
    single bad item or page never aborts the whole source.
    """

    source_name: str = ""
    item_selector: str = ""
    next_page_selector: str = "li.next > a"

    def __init__(self, client: HttpClient, start_url: str, max_pages: int | None = None) -> None:
        self.client = client
        self.start_url = start_url
        self.max_pages = max_pages
        self.stats = ScrapeStats()
        self.records: list[dict[str, Any]] = []
        self.logger = logging.getLogger(f"scrapers.{self.source_name}")

    # ----------------------------------------------------------------- fetching
    def get_soup(self, url: str) -> BeautifulSoup:
        """Fetch ``url`` and parse it.

        The raw bytes are handed to BeautifulSoup (not ``response.text``) so the
        page's own ``<meta charset>`` decides the encoding. Books to Scrape
        sends ``Content-Type: text/html`` with no charset, which would make
        ``requests`` fall back to ISO-8859-1 and turn "£" into "Â£".
        """
        response = self.client.get(url)
        return BeautifulSoup(response.content, "lxml")

    # --------------------------------------------------------------- pagination
    def next_page_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        link = soup.select_one(self.next_page_selector)
        href = link.get("href") if link else None
        return urljoin(current_url, href) if href else None

    def scrape(self) -> list[dict[str, Any]]:
        """Crawl every page reachable through next links; return raw records."""
        url: str | None = self.start_url
        visited: set[str] = set()
        self.logger.info("Starting %s at %s", self.source_name, self.start_url)

        while url:
            if self.max_pages is not None and self.stats.pages_scraped >= self.max_pages:
                self.stats.stop_reason = "max_pages_reached"
                self.logger.info("Reached max_pages=%d; stopping", self.max_pages)
                break
            if url in visited:
                self.stats.stop_reason = "pagination_loop_detected"
                self.logger.warning("Next link points to an already visited page %s; stopping", url)
                break
            visited.add(url)

            try:
                soup = self.get_soup(url)
            except FetchError as exc:
                # Without this page we cannot discover the next link, so the
                # crawl of this source ends here; records so far are kept.
                self.stats.pages_failed += 1
                self.stats.failed_urls.append(url)
                self.stats.stop_reason = "page_fetch_failed"
                self.logger.error("Could not load page %s (%s); stopping this source", url, exc.reason)
                break

            page_records = self.parse_page(soup, url)
            self.records.extend(page_records)
            self.stats.pages_scraped += 1
            self.stats.first_page_url = self.stats.first_page_url or url
            self.stats.last_page_url = url
            self.logger.info(
                "Scraped page %d (%s): %d records", self.stats.pages_scraped, url, len(page_records)
            )

            next_url = self.next_page_url(soup, url)
            if next_url:
                self.stats.next_links_followed += 1
            else:
                self.stats.stop_reason = "no_next_link"
            url = next_url

        self.logger.info(
            "Finished %s: %d pages, %d raw records (stop reason: %s)",
            self.source_name, self.stats.pages_scraped, len(self.records), self.stats.stop_reason,
        )
        return self.records

    # ------------------------------------------------------------------ parsing
    def parse_page(self, soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
        items = soup.select(self.item_selector)
        if not items:
            self.logger.warning("No items matched %r on %s", self.item_selector, page_url)
        self.stats.items_found += len(items)

        records = []
        for index, item in enumerate(items, start=1):
            try:
                record = self.parse_item(item, page_url)
            except PARSE_ERRORS as exc:
                # Keep a placeholder so the failure is counted and reported as a
                # rejected "malformed_record" instead of silently vanishing.
                self.stats.malformed_items += 1
                self.logger.warning("Malformed item #%d on %s: %r", index, page_url, exc)
                record = empty_record(self.source_name, page_url)
                record[PARSE_ERROR_KEY] = f"{exc.__class__.__name__}: {exc}"
            else:
                self.enrich(record)
            records.append(record)
        return records

    def warn_missing(self, what: str, page_url: str) -> None:
        self.logger.warning("Missing expected element %s on %s", what, page_url)

    @staticmethod
    def text_of(element: Tag | None) -> str | None:
        return element.get_text() if element is not None else None

    @abstractmethod
    def parse_item(self, item: Tag, page_url: str) -> dict[str, Any]:
        """Turn one listing element into a raw (uncleaned) schema record."""

    def enrich(self, record: dict[str, Any]) -> None:
        """Optional hook for extra requests per record (e.g. detail pages)."""
