"""Books to Scrape (https://books.toscrape.com/)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from schema import BOOKS_SOURCE, empty_record
from scrapers.base_scraper import PARSE_ERRORS, BaseScraper
from scrapers.http_client import FetchError, HttpClient


class BooksScraper(BaseScraper):
    """Listing pages give title, price, rating and the detail URL.

    Category (breadcrumb) and description exist only on each book's detail
    page, so when ``fetch_details`` is on, one extra request is made per book.
    If that request fails the listing data is kept and the two fields stay
    empty.
    """

    source_name = BOOKS_SOURCE
    item_selector = "article.product_pod"

    def __init__(
        self,
        client: HttpClient,
        start_url: str,
        max_pages: int | None = None,
        fetch_details: bool = True,
    ) -> None:
        super().__init__(client, start_url, max_pages)
        self.fetch_details = fetch_details
        self.stats.extra.update(detail_pages_fetched=0, detail_pages_failed=0)

    def parse_item(self, item: Tag, page_url: str) -> dict[str, Any]:
        link = item.select_one("h3 > a")
        if link is None:
            self.warn_missing("h3 > a", page_url)
        href = link.get("href") if link else None
        record = empty_record(self.source_name, urljoin(page_url, href) if href else None)

        # The visible link text is truncated ("A Light in the ..."); the full
        # title lives in the title attribute.
        if link is not None:
            record["name_or_title"] = link.get("title") or link.get_text()

        price = item.select_one("p.price_color")
        if price is None:
            self.warn_missing("p.price_color", page_url)
        record["price"] = self.text_of(price)

        rating = item.select_one("p.star-rating")
        if rating is None:
            self.warn_missing("p.star-rating", page_url)
        else:
            # <p class="star-rating Three"> -> "Three"
            words = [c for c in rating.get("class", []) if c != "star-rating"]
            record["rating"] = words[0] if words else None
        return record

    def enrich(self, record: dict[str, Any]) -> None:
        if not self.fetch_details or not record.get("source_url"):
            return
        url = record["source_url"]
        try:
            soup = self.get_soup(url)
            record.update(parse_book_detail(soup))
        except FetchError as exc:
            self.stats.extra["detail_pages_failed"] += 1
            self.logger.warning("Detail page failed for %s (%s); category/description left empty", url, exc.reason)
            return
        except PARSE_ERRORS as exc:
            self.stats.extra["detail_pages_failed"] += 1
            self.logger.warning("Could not parse detail page %s: %r", url, exc)
            return
        self.stats.extra["detail_pages_fetched"] += 1
        self.logger.debug("Fetched detail page %s", url)


def parse_book_detail(soup: BeautifulSoup) -> dict[str, str | None]:
    """Extract category and description from a book detail page.

    Breadcrumb links are Home > Books > <Category>; the description is the
    paragraph immediately after ``#product_description`` and is genuinely
    absent for a few books.
    """
    crumbs = soup.select("ul.breadcrumb li a")
    category = crumbs[2].get_text() if len(crumbs) >= 3 else None
    description = soup.select_one("#product_description + p")
    return {
        "category": category,
        "description": description.get_text() if description is not None else None,
    }
