"""Writing datasets and reports to disk (UTF-8, deterministic column order)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

TAG_SEPARATOR = "|"


def _cell(value: Any) -> str:
    """Serialise one value for CSV: None -> "", lists -> "a|b", floats -> 2dp."""
    if value is None:
        return ""
    if isinstance(value, list):
        return TAG_SEPARATOR.join(str(v) for v in value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def write_csv(records: Iterable[dict[str, Any]], path: Path, fieldnames: Iterable[str]) -> int:
    """Write ``records`` with exactly ``fieldnames`` as columns; return row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({col: _cell(record.get(col)) for col in columns})
            count += 1
    return count


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
