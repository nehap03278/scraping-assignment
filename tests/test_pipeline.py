"""End-to-end pipeline tests with offline fake sources."""

import csv
import json

from config import Settings
from pipeline import run_pipeline
from schema import FIELDNAMES
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

BOOKS = "https://books.toscrape.com/"
QUOTES = "https://quotes.toscrape.com/"
QUOTES_P2 = "https://quotes.toscrape.com/page/2/"


class ExplodingScraper(BooksScraper):
    def scrape(self):
        raise RuntimeError("simulated bug in books scraper")


def settings_for(tmp_path):
    return Settings(output_dir=tmp_path / "output", log_file=tmp_path / "logs" / "scraper.log")


def quotes_scraper(fake_client_factory, extra=None):
    client = fake_client_factory({QUOTES: "quotes_page1.html", QUOTES_P2: extra or "quotes_page2.html"})
    return QuotesScraper(client, QUOTES)


def test_full_offline_run_reconciles_and_writes_outputs(tmp_path, fake_client_factory):
    books_client = fake_client_factory({
        BOOKS: "books_page1.html",
        "https://books.toscrape.com/catalogue/page-2.html": "books_page2.html",
    })
    scrapers = [BooksScraper(books_client, BOOKS, fetch_details=False), quotes_scraper(fake_client_factory)]
    summary = run_pipeline(settings_for(tmp_path), scrapers=scrapers)

    totals = summary["totals"]
    # 3 books (one without price) + 3 quotes (one without author)
    assert totals == {
        "raw_records": 6, "cleaned_records": 6, "valid_records": 4,
        "rejected_records": 2, "duplicate_records": 0, "final_records": 4,
    }
    assert summary["rejection_reasons"] == {"missing_author": 1, "missing_price": 1}
    assert summary["reconciliation"]["balanced"] is True
    assert all(summary["reconciliation"]["per_source_balanced"].values())
    assert summary["sources"]["books_toscrape"]["pages_scraped"] == 2
    assert summary["run"]["status"] == "success"

    out = tmp_path / "output"
    with (out / "final_dataset.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0].keys()) == FIELDNAMES
    assert len(rows) == 4
    assert rows[0]["price"] == "51.77" and rows[0]["rating"] == "3"
    assert {r["source"] for r in rows} == {"books_toscrape", "quotes_toscrape"}

    with (out / "rejected_records.csv").open(encoding="utf-8", newline="") as handle:
        rejected = list(csv.DictReader(handle))
    assert sorted(r["rejection_reasons"] for r in rejected) == ["missing_author", "missing_price"]
    assert json.loads((out / "summary_report.json").read_text(encoding="utf-8")) == summary


def test_one_source_failing_does_not_stop_the_other(tmp_path, fake_client_factory, caplog):
    scrapers = [
        ExplodingScraper(fake_client_factory({}), BOOKS, fetch_details=False),
        quotes_scraper(fake_client_factory),
    ]
    summary = run_pipeline(settings_for(tmp_path), scrapers=scrapers)
    assert summary["sources"]["books_toscrape"]["status"] == "failed"
    assert "simulated bug" in summary["sources"]["books_toscrape"]["error"]
    assert summary["sources"]["quotes_toscrape"]["status"] == "ok"
    assert summary["totals"]["final_records"] == 2
    assert summary["run"]["status"] == "partial"
    assert "Unexpected failure while scraping books_toscrape" in caplog.text


def test_unreachable_source_is_reported_as_failed(tmp_path, fake_client_factory):
    scrapers = [
        BooksScraper(fake_client_factory({}), BOOKS, fetch_details=False),  # every request 404s
        quotes_scraper(fake_client_factory),
    ]
    summary = run_pipeline(settings_for(tmp_path), scrapers=scrapers)
    books = summary["sources"]["books_toscrape"]
    assert books["status"] == "failed" and books["pages_failed"] == 1
    assert summary["sources"]["quotes_toscrape"]["final_records"] == 2


def test_duplicates_are_counted_and_reported(tmp_path, fake_client_factory):
    # Serve page 1's quotes again as page 2 (minus its next link), so the same
    # quote appears on two URLs. Real site data is never altered for this.
    client = fake_client_factory({QUOTES: "quotes_page1.html"})
    client.pages[QUOTES_P2] = client.pages[QUOTES].replace(b'<li class="next">', b"<li>")
    summary = run_pipeline(settings_for(tmp_path), scrapers=[QuotesScraper(client, QUOTES)])
    assert summary["totals"]["duplicate_records"] == 1
    assert summary["duplicates"]["by_source"] == {"quotes_toscrape": 1}
    assert summary["reconciliation"]["balanced"] is True
    with (tmp_path / "output" / "duplicates.csv").open(encoding="utf-8", newline="") as handle:
        dup = next(csv.DictReader(handle))
    assert dup["source_url"] == QUOTES_P2 and dup["duplicate_of"] == QUOTES
