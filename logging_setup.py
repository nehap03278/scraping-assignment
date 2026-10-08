"""Logging configuration: full log file plus a concise console stream."""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(log_file: Path, verbose: bool = False) -> None:
    """Send INFO+ (DEBUG+ when verbose) to ``log_file`` and to the console.

    The file is overwritten on each run so it always matches the latest
    ``summary_report.json``.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    # urllib3 logs every retry at DEBUG/WARNING; keep its retry warnings only.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
