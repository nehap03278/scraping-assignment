"""Quotes to Scrape (https://quotes.toscrape.com/)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from schema import QUOTES_SOURCE, empty_record
from scrapers.base_scraper import BaseScraper


class QuotesScraper(BaseScraper):
    """Every quote is fully described on the listing page.

    Mapping into the common schema: quote text -> ``name_or_title``; the
    listing page URL -> ``source_url`` (quotes have no page of their own);
    category, price, rating and description do not exist and stay empty.
    """

    source_name = QUOTES_SOURCE
    item_selector = "div.quote"

    def parse_item(self, item: Tag, page_url: str) -> dict[str, Any]:
        record = empty_record(self.source_name, page_url)

        text = item.select_one("span.text")
        if text is None:
            self.warn_missing("span.text", page_url)
        record["name_or_title"] = self.text_of(text)

        author = item.select_one("small.author")
        if author is None:
            self.warn_missing("small.author", page_url)
        record["author"] = self.text_of(author)

        author_link = item.select_one('a[href^="/author/"]')
        if author_link is not None and author_link.get("href"):
            record["author_url"] = urljoin(page_url, author_link["href"])

        record["tags"] = [tag.get_text() for tag in item.select("a.tag")]
        return record
