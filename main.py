"""Command-line entry point: ``python main.py [options]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import Settings
from logging_setup import configure_logging
from pipeline import run_pipeline


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return number


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return number


def non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = Settings()
    parser = argparse.ArgumentParser(
        description="Scrape Books to Scrape and Quotes to Scrape into one cleaned, validated, de-duplicated dataset."
    )
    parser.add_argument("--sources", nargs="+", choices=("books", "quotes"), default=list(defaults.sources),
                        help="sources to scrape (default: both)")
    parser.add_argument("--max-pages", type=positive_int, default=None,
                        help="stop each source after N listing pages (default: follow next links to the end)")
    parser.add_argument("--skip-book-details", action="store_true",
                        help="do not open book detail pages (faster; category and description stay empty)")
    parser.add_argument("--delay", type=non_negative_float, default=defaults.request_delay,
                        help=f"minimum seconds between requests (default: {defaults.request_delay})")
    parser.add_argument("--timeout", type=positive_float, default=defaults.timeout,
                        help=f"per-request timeout in seconds (default: {defaults.timeout})")
    parser.add_argument("--retries", type=non_negative_int, default=defaults.max_retries,
                        help=f"retries for connection errors and HTTP 429/5xx (default: {defaults.max_retries})")
    parser.add_argument("--books-url", default=defaults.books_start_url, help="Books to Scrape start URL")
    parser.add_argument("--quotes-url", default=defaults.quotes_start_url, help="Quotes to Scrape start URL")
    parser.add_argument("--output-dir", type=Path, default=defaults.output_dir, help="directory for output files")
    parser.add_argument("--log-file", type=Path, default=defaults.log_file, help="log file path")
    parser.add_argument("--verbose", action="store_true", help="also log DEBUG messages")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings(
        books_start_url=args.books_url,
        quotes_start_url=args.quotes_url,
        sources=tuple(dict.fromkeys(args.sources)),
        request_delay=args.delay,
        timeout=args.timeout,
        max_retries=args.retries,
        max_pages=args.max_pages,
        fetch_book_details=not args.skip_book_details,
        output_dir=args.output_dir,
        log_file=args.log_file,
    )
    configure_logging(settings.log_file, verbose=args.verbose)
    summary = run_pipeline(settings)
    totals = summary["totals"]
    print(
        f"\nStatus: {summary['run']['status']} | raw {totals['raw_records']} | "
        f"rejected {totals['rejected_records']} | duplicates {totals['duplicate_records']} | "
        f"final {totals['final_records']} | see {summary['outputs']['summary_report']}"
    )
    return 1 if summary["run"]["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
