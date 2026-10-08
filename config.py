"""Central, overridable runtime settings for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

BOOKS_START_URL = "https://books.toscrape.com/"
QUOTES_START_URL = "https://quotes.toscrape.com/"

# Temporary failures worth retrying (rate limiting and transient server errors).
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class Settings:
    """All tunable knobs in one place; main.py builds this from CLI arguments."""

    books_start_url: str = BOOKS_START_URL
    quotes_start_url: str = QUOTES_START_URL
    sources: tuple[str, ...] = ("books", "quotes")

    # Politeness / robustness of the HTTP layer.
    request_delay: float = 0.5
    timeout: float = 10.0
    max_retries: int = 3
    backoff_factor: float = 1.0
    user_agent: str = (
        "ScrapingAssignmentBot/1.0 (+educational exercise; "
        "python-requests; respects rate limits)"
    )

    # Crawl scope. None means "follow next links until there are none".
    max_pages: int | None = None
    fetch_book_details: bool = True

    # Output locations.
    output_dir: Path = PROJECT_ROOT / "output"
    log_file: Path = PROJECT_ROOT / "logs" / "scraper.log"
