"""Source-specific scrapers built on a shared HTTP client and base crawler."""

from scrapers.base_scraper import BaseScraper, ScrapeStats
from scrapers.books_scraper import BooksScraper
from scrapers.http_client import FetchError, HttpClient
from scrapers.quotes_scraper import QuotesScraper

__all__ = ["BaseScraper", "BooksScraper", "FetchError", "HttpClient", "QuotesScraper", "ScrapeStats"]
