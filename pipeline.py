"""Orchestration: scrape -> clean -> validate -> deduplicate -> consolidate -> report."""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT, Settings
from processing.cleaning import clean_record
from processing.deduplication import QUOTE_PREFIX_CHARS, deduplicate
from processing.output import write_csv, write_json
from processing.validation import partition_valid
from schema import FIELDNAMES, PARSE_ERROR_KEY
from scrapers import BaseScraper, BooksScraper, HttpClient, QuotesScraper

logger = logging.getLogger("pipeline")

DATASET_FILE = "final_dataset.csv"
SUMMARY_FILE = "summary_report.json"
REJECTED_FILE = "rejected_records.csv"
DUPLICATES_FILE = "duplicates.csv"


def build_scrapers(settings: Settings, client: HttpClient) -> list[BaseScraper]:
    factories = {
        "books": lambda: BooksScraper(
            client, settings.books_start_url, settings.max_pages, settings.fetch_book_details
        ),
        "quotes": lambda: QuotesScraper(client, settings.quotes_start_url, settings.max_pages),
    }
    return [factories[name]() for name in settings.sources]


def run_scraper(scraper: BaseScraper) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run one source in isolation. Never raises: a failure is logged, recorded
    in the report and the pipeline moves on to the next source."""
    error = None
    try:
        scraper.scrape()
    except Exception as exc:  # noqa: BLE001 - source boundary, logged with traceback
        error = f"{exc.__class__.__name__}: {exc}"
        logger.exception("Unexpected failure while scraping %s; continuing with other sources", scraper.source_name)

    stats = scraper.stats
    if stats.pages_scraped == 0:
        status = "failed"
        error = error or f"no pages could be scraped ({stats.stop_reason})"
    elif error or stats.pages_failed:
        status = "partial"
    else:
        status = "ok"
    if status != "ok":
        logger.error("Source %s finished with status %s: %s", scraper.source_name, status, error or stats.stop_reason)

    report = {"status": status, "error": error, **stats.to_dict(), "raw_records": len(scraper.records)}
    return scraper.records, report


def clean_all(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for raw in raw_records:
        try:
            cleaned.append(clean_record(raw))
        except (AttributeError, TypeError, ValueError) as exc:
            logger.warning("Could not clean record %r: %r", raw, exc)
            source = raw.get("source") if isinstance(raw, dict) else None
            cleaned.append({"source": source, PARSE_ERROR_KEY: f"cleaning failed: {exc!r}"})
    return cleaned


def count_by_source(records: list[dict[str, Any]]) -> Counter:
    return Counter(record.get("source") for record in records)


def missing_value_report(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per source, how many final records have each field empty (data-quality view)."""
    report: dict[str, dict[str, int]] = {}
    for record in records:
        per_source = report.setdefault(record["source"], {field: 0 for field in FIELDNAMES})
        for field in FIELDNAMES:
            if record.get(field) in (None, "", []):
                per_source[field] += 1
    return report


def run_pipeline(settings: Settings, scrapers: list[BaseScraper] | None = None) -> dict[str, Any]:
    """Execute the whole pipeline and return the summary that was written."""
    started_at = datetime.now(timezone.utc)
    started_clock = time.perf_counter()
    logger.info("Pipeline started (sources: %s)", ", ".join(settings.sources))

    client = HttpClient(
        user_agent=settings.user_agent,
        timeout=settings.timeout,
        delay=settings.request_delay,
        max_retries=settings.max_retries,
        backoff_factor=settings.backoff_factor,
    )
    try:
        scrapers = scrapers if scrapers is not None else build_scrapers(settings, client)

        # 1. Scrape each source independently.
        raw_records: list[dict[str, Any]] = []
        source_reports: dict[str, dict[str, Any]] = {}
        for scraper in scrapers:
            logger.info("=== Source start: %s ===", scraper.source_name)
            records, report = run_scraper(scraper)
            raw_records.extend(records)
            source_reports[scraper.source_name] = report
            logger.info("=== Source end: %s (%s, %d raw records) ===", scraper.source_name, report["status"], len(records))
    finally:
        client.close()

    # 2. Clean.
    logger.info("Cleaning %d raw records", len(raw_records))
    cleaned = clean_all(raw_records)

    # 3. Validate.
    logger.info("Validating %d cleaned records", len(cleaned))
    valid, rejected = partition_valid(cleaned)
    for record in rejected:
        logger.warning(
            "Rejected record from %s (%s): %s",
            record.get("source"), record.get("source_url"), ", ".join(record["rejection_reasons"]),
        )
    logger.info("Validation: %d valid, %d rejected", len(valid), len(rejected))

    # 4. Deduplicate.
    logger.info("Deduplicating %d valid records", len(valid))
    final, duplicates = deduplicate(valid)
    for dup in duplicates:
        logger.info("Duplicate removed: %r (%s) duplicates %s", dup["name_or_title"], dup["source_url"], dup["duplicate_of"])
    logger.info("Deduplication: %d unique, %d duplicates", len(final), len(duplicates))

    # 5. Consolidate and write outputs.
    out = settings.output_dir
    write_csv(final, out / DATASET_FILE, FIELDNAMES)
    write_csv(rejected, out / REJECTED_FILE, (*FIELDNAMES, "rejection_reasons", PARSE_ERROR_KEY))
    write_csv(duplicates, out / DUPLICATES_FILE, (*FIELDNAMES, "fingerprint", "duplicate_of"))
    logger.info("Wrote %d records to %s", len(final), out / DATASET_FILE)

    # 6. Summary metrics, all derived from the lists above.
    raw_by, rejected_by, dup_by, final_by = map(count_by_source, (raw_records, rejected, duplicates, final))
    for name, report in source_reports.items():
        report.update(
            rejected_records=rejected_by[name],
            duplicate_records=dup_by[name],
            final_records=final_by[name],
        )
    statuses = {r["status"] for r in source_reports.values()}
    run_status = "success" if statuses == {"ok"} else "failed" if statuses <= {"failed"} else "partial"
    totals = {
        "raw_records": len(raw_records),
        "cleaned_records": len(cleaned),
        "valid_records": len(valid),
        "rejected_records": len(rejected),
        "duplicate_records": len(duplicates),
        "final_records": len(final),
    }
    finished_at = datetime.now(timezone.utc)
    summary = {
        "run": {
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round(time.perf_counter() - started_clock, 2),
            "status": run_status,
            "settings": _settings_for_report(settings),
        },
        "totals": totals,
        "sources": source_reports,
        "rejection_reasons": dict(sorted(Counter(
            reason for record in rejected for reason in record["rejection_reasons"]
        ).items())),
        "duplicates": {
            "total": len(duplicates),
            "by_source": dict(sorted(dup_by.items())),
            "strategy": {
                "books_toscrape": "sha256(source | normalised title)",
                "quotes_toscrape": f"sha256(source | normalised author | first {QUOTE_PREFIX_CHARS} chars of normalised quote)",
                "normalisation": "casefold, strip accents, punctuation/symbols -> space, collapse whitespace",
            },
        },
        "reconciliation": {
            "formula": "raw_records == rejected_records + duplicate_records + final_records",
            "balanced": totals["raw_records"] == totals["rejected_records"] + totals["duplicate_records"] + totals["final_records"],
            "per_source_balanced": {
                name: raw_by[name] == rejected_by[name] + dup_by[name] + final_by[name] for name in source_reports
            },
        },
        "data_quality": {"empty_fields_in_final_dataset": missing_value_report(final)},
        "outputs": {
            "final_dataset": _relative(out / DATASET_FILE),
            "summary_report": _relative(out / SUMMARY_FILE),
            "rejected_records": _relative(out / REJECTED_FILE),
            "duplicates": _relative(out / DUPLICATES_FILE),
            "log_file": _relative(settings.log_file),
        },
        "http": {"requests_made": client.requests_made, "failed_requests": client.failed_requests},
    }
    write_json(summary, out / SUMMARY_FILE)
    logger.info("Wrote summary to %s", out / SUMMARY_FILE)
    logger.info(
        "Pipeline finished with status %s in %.1fs: raw=%d rejected=%d duplicates=%d final=%d",
        run_status, summary["run"]["duration_seconds"], totals["raw_records"],
        totals["rejected_records"], totals["duplicate_records"], totals["final_records"],
    )
    return summary


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _settings_for_report(settings: Settings) -> dict[str, Any]:
    data = asdict(settings)
    data["output_dir"] = _relative(settings.output_dir)
    data["log_file"] = _relative(settings.log_file)
    data["sources"] = list(settings.sources)
    return data
