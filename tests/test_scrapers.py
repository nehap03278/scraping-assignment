"""Offline scraper tests against saved HTML that mirrors the live markup."""

from schema import PARSE_ERROR_KEY
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

BOOKS = "https://books.toscrape.com/"
BOOKS_P2 = "https://books.toscrape.com/catalogue/page-2.html"
LIGHT_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
QUOTES = "https://quotes.toscrape.com/"
QUOTES_P2 = "https://quotes.toscrape.com/page/2/"


def books_scraper(fake_client_factory, extra_pages=None, **kwargs):
    pages = {BOOKS: "books_page1.html", BOOKS_P2: "books_page2.html", **(extra_pages or {})}
    client = fake_client_factory(pages)
    return BooksScraper(client, BOOKS, **kwargs), client


class TestBooksScraper:
    def test_follows_next_links_until_none(self, fake_client_factory):
        scraper, client = books_scraper(fake_client_factory, fetch_details=False)
        records = scraper.scrape()
        assert client.requested == [BOOKS, BOOKS_P2]
        assert len(records) == 3
        assert scraper.stats.pages_scraped == 2
        assert scraper.stats.next_links_followed == 1
        assert scraper.stats.stop_reason == "no_next_link"

    def test_relative_links_are_resolved_against_current_page(self, fake_client_factory):
        scraper, _ = books_scraper(fake_client_factory, fetch_details=False)
        records = scraper.scrape()
        assert records[0]["source_url"] == LIGHT_URL
        # page-2 uses a link relative to /catalogue/
        assert records[2]["source_url"] == "https://books.toscrape.com/catalogue/sharp-objects_997/index.html"

    def test_extracts_full_title_price_and_rating(self, fake_client_factory):
        scraper, _ = books_scraper(fake_client_factory, fetch_details=False)
        first = scraper.scrape()[0]
        assert first["name_or_title"] == "A Light in the Attic"  # not the truncated link text
        assert first["price"] == "£51.77"  # UTF-8 bytes decoded via <meta charset>
        assert first["rating"] == "Three"
        assert first["source"] == "books_toscrape"
        assert first["category"] is None and first["description"] is None

    def test_missing_price_element_leaves_none(self, fake_client_factory, caplog):
        scraper, _ = books_scraper(fake_client_factory, fetch_details=False)
        second = scraper.scrape()[1]
        assert second["price"] is None
        assert "Missing expected element p.price_color" in caplog.text

    def test_max_pages_limits_crawl(self, fake_client_factory):
        scraper, client = books_scraper(fake_client_factory, fetch_details=False, max_pages=1)
        scraper.scrape()
        assert client.requested == [BOOKS]
        assert scraper.stats.stop_reason == "max_pages_reached"

    def test_detail_pages_add_category_and_description(self, fake_client_factory):
        scraper, _ = books_scraper(fake_client_factory, extra_pages={LIGHT_URL: "book_detail.html"})
        records = scraper.scrape()
        assert records[0]["category"] == "Poetry"
        assert records[0]["description"].startswith("It's hard to imagine")
        assert scraper.stats.extra["detail_pages_fetched"] == 1

    def test_failed_detail_page_keeps_listing_data(self, fake_client_factory, caplog):
        # Only one detail page exists in the fake; the other two 404.
        scraper, _ = books_scraper(fake_client_factory, extra_pages={LIGHT_URL: "book_detail.html"})
        records = scraper.scrape()
        assert len(records) == 3
        assert records[2]["name_or_title"] == "Sharp Objects"
        assert records[2]["category"] is None
        assert scraper.stats.extra["detail_pages_failed"] == 2
        assert "Detail page failed" in caplog.text

    def test_book_without_description_stays_empty(self, fake_client_factory):
        scraper, _ = books_scraper(fake_client_factory, extra_pages={LIGHT_URL: "book_detail_no_description.html"})
        first = scraper.scrape()[0]
        assert first["category"] == "Default"
        assert first["description"] is None

    def test_failed_page_stops_source_but_keeps_earlier_records(self, fake_client_factory, caplog):
        client = fake_client_factory({BOOKS: "books_page1.html"})  # page 2 missing
        scraper = BooksScraper(client, BOOKS, fetch_details=False)
        records = scraper.scrape()
        assert len(records) == 2
        assert scraper.stats.pages_failed == 1
        assert scraper.stats.stop_reason == "page_fetch_failed"
        assert "Could not load page" in caplog.text

    def test_malformed_item_becomes_placeholder_not_crash(self, fake_client_factory, monkeypatch):
        scraper, _ = books_scraper(fake_client_factory, fetch_details=False)
        original = BooksScraper.parse_item

        def flaky(self, item, page_url):
            if "Sharp Objects" in item.get_text():
                raise ValueError("unexpected markup")
            return original(self, item, page_url)

        monkeypatch.setattr(BooksScraper, "parse_item", flaky)
        records = scraper.scrape()
        assert len(records) == 3
        assert records[2][PARSE_ERROR_KEY] == "ValueError: unexpected markup"
        assert scraper.stats.malformed_items == 1

    def test_pagination_loop_is_detected(self, fake_client_factory):
        looping = b'<html><body><li class="next"><a href="/">next</a></li></body></html>'
        client = fake_client_factory({BOOKS: looping})
        scraper = BooksScraper(client, BOOKS, fetch_details=False)
        scraper.scrape()
        assert scraper.stats.stop_reason == "pagination_loop_detected"
        assert client.requested == [BOOKS]


class TestQuotesScraper:
    def scrape(self, fake_client_factory):
        client = fake_client_factory({QUOTES: "quotes_page1.html", QUOTES_P2: "quotes_page2.html"})
        scraper = QuotesScraper(client, QUOTES)
        return scraper, scraper.scrape(), client

    def test_follows_next_links_until_none(self, fake_client_factory):
        scraper, records, client = self.scrape(fake_client_factory)
        assert client.requested == [QUOTES, QUOTES_P2]
        assert len(records) == 3
        assert scraper.stats.stop_reason == "no_next_link"

    def test_extracts_text_author_url_and_tags(self, fake_client_factory):
        _, records, _ = self.scrape(fake_client_factory)
        first = records[0]
        assert first["name_or_title"] == "“The world as we have created it is a process of our thinking.”"
        assert first["author"] == "Albert Einstein"
        assert first["author_url"] == "https://quotes.toscrape.com/author/Albert-Einstein"
        assert first["tags"] == ["change", "Deep-Thoughts"]
        assert first["source_url"] == QUOTES
        assert records[2]["source_url"] == QUOTES_P2

    def test_fields_quotes_do_not_have_stay_empty(self, fake_client_factory):
        _, records, _ = self.scrape(fake_client_factory)
        for record in records:
            assert record["price"] is None
            assert record["rating"] is None
            assert record["category"] is None
            assert record["description"] is None

    def test_missing_author_is_none_and_logged(self, fake_client_factory, caplog):
        _, records, _ = self.scrape(fake_client_factory)
        assert records[1]["author"] is None
        assert records[1]["author_url"] is None
        assert records[1]["tags"] == []
        assert "Missing expected element small.author" in caplog.text
