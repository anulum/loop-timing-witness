# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — validated atomic daily PyPI download history

"""Import project-bound PyPIStats observations without fabricating missing counts."""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import os
import sys
import tempfile
from datetime import UTC, date, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PACKAGE = "loop-timing-witness"
CSV_PATH = Path("downloads/loop-timing-witness.csv")
SOURCE_URL = f"https://pypistats.org/api/packages/{PACKAGE}/overall"
MAX_BYTES = 1_000_000
MAX_HTTP_STATUS = 600
CATEGORIES = ("without_mirrors", "with_mirrors")
HEADER = ("date", *CATEGORIES)
Rows = dict[str, dict[str, int]]


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON names before identity or count validation."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            msg = f"duplicate JSON name: {key}"
            raise ValueError(msg)
        result[key] = value
    return result


def _records(payload: object) -> list[Any]:
    """Validate the exact project/type envelope before processing observations."""
    if not isinstance(payload, dict) or set(payload) != {"package", "type", "data"}:
        msg = "invalid response object schema"
        raise ValueError(msg)
    if payload["package"] != PACKAGE or payload["type"] != "overall_downloads":
        msg = "response identity mismatch"
        raise ValueError(msg)
    records = payload["data"]
    if not isinstance(records, list) or not records:
        msg = "response data must be a non-empty list"
        raise ValueError(msg)
    return records


def _rows(payload: object) -> Rows:
    """Validate every sparse observation against its retained-history contract."""
    records = _records(payload)
    rows: Rows = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"category", "date", "downloads"}:
            msg = "invalid observation object schema"
            raise ValueError(msg)
        category, day, count = record["category"], record["date"], record["downloads"]
        if not isinstance(category, str) or category not in CATEGORIES:
            msg = "invalid observation category"
            raise ValueError(msg)
        if not isinstance(day, str):
            msg = "invalid observation date"
            raise ValueError(msg)
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day or parsed > datetime.now(UTC).date():
            msg = "invalid observation date"
            raise ValueError(msg)
        if type(count) is not int or not 0 <= count <= 2**63 - 1:
            msg = "invalid observation count"
            raise ValueError(msg)
        values = rows.setdefault(day, {})
        if category in values:
            msg = "duplicate date/category observation"
            raise ValueError(msg)
        values[category] = count
    for values in rows.values():
        if (
            "with_mirrors" not in values
            or values.get("without_mirrors", 0) > values["with_mirrors"]
        ):
            msg = "missing or inconsistent mirror counts"
            raise ValueError(msg)
    return rows


def _count(raw: object) -> int:
    """Require a canonical decimal count in the retained CSV."""
    if not isinstance(raw, str):
        msg = "missing retained count"
        raise ValueError(msg)
    count = int(raw)
    if str(count) != raw:
        msg = "noncanonical retained count"
        raise ValueError(msg)
    return count


def _existing(path: Path) -> Rows:
    """Validate retained history before any atomic replacement."""
    if path.is_symlink():
        msg = "CSV target must not be a symlink"
        raise ValueError(msg)
    if not path.exists():
        return {}
    records = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != HEADER:
            msg = "invalid retained CSV header"
            raise ValueError(msg)
        for row in reader:
            if set(row) != set(HEADER):
                msg = "invalid retained CSV fields"
                raise ValueError(msg)
            for category in CATEGORIES:
                raw = row[category]
                if category == "without_mirrors" and raw == "":
                    continue
                count = _count(raw)
                records.append({"category": category, "date": row["date"], "downloads": count})
    if not records:
        return {}
    return _rows({"package": PACKAGE, "type": "overall_downloads", "data": records})


def _write(path: Path, rows: Rows) -> None:
    """Flush a complete sorted CSV and replace only its selected target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            for day, values in sorted(rows.items()):
                writer.writerow((day, *(values.get(category, "") for category in CATEGORIES)))
            stream.flush()
            os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def fetch(url: str = SOURCE_URL) -> bytes | None:
    """Read one bounded HTTP(S) response; known temporary absence produces no observations.

    Parameters
    ----------
    url
        Provider endpoint or an explicitly selected transport endpoint for imported observations.

    Returns
    -------
    bytes or None
        JSON response bytes, or unavailable data for 404, 429 and server failures.

    Raises
    ------
    ValueError
        If the URL, status, content type or size is invalid.
    OSError
        If the selected network transport cannot complete.
    """
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.fragment
        or "\r" in url
        or "\n" in url
    ):
        msg = "source URL must be an uncredentialed HTTP(S) endpoint"
        raise ValueError(msg)
    kind = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = kind(parsed.hostname, parsed.port, timeout=15)
    try:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        connection.request("GET", target, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if (
            response.status in {404, 429}
            or HTTPStatus.INTERNAL_SERVER_ERROR <= response.status < MAX_HTTP_STATUS
        ):
            return None
        if response.status != HTTPStatus.OK:
            msg = f"provider returned HTTP {response.status}"
            raise ValueError(msg)
        if not response.getheader("Content-Type", "").lower().startswith("application/json"):
            msg = "provider response is not JSON"
            raise ValueError(msg)
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            msg = "provider response exceeds size bound"
            raise ValueError(msg)
        return body
    finally:
        connection.close()


def snapshot(body: bytes, path: Path) -> int:
    """Validate and upsert a response into real retained history using atomic replacement.

    Parameters
    ----------
    body
        Complete project-specific overall-downloads JSON response.
    path
        Selected CSV target; symlinks and malformed existing history are refused.

    Returns
    -------
    int
        Number of retained observation dates, including earlier snapshots.

    Raises
    ------
    ValueError
        If response or retained data has invalid identity, schema or values.
    OSError
        If the actual CSV update cannot complete.
    """
    if len(body) > MAX_BYTES:
        msg = "response exceeds size bound"
        raise ValueError(msg)
    fresh = _rows(json.loads(body, object_pairs_hook=_unique))
    rows = _existing(path)
    rows.update(fresh)
    _write(path, rows)
    return len(rows)


def _request(args: argparse.Namespace) -> dict[str, str | int]:
    """Read explicit source arguments and retain or update actual history."""
    if args.project_csv_only and args.csv != CSV_PATH:
        msg = "workflow CSV target must be downloads/loop-timing-witness.csv"
        raise ValueError(msg)
    existing = _existing(args.csv)
    body = args.response.read_bytes() if args.response else fetch(args.url)
    if body is None:
        if not args.allow_missing:
            msg = "provider data unavailable; no download count inferred"
            raise ValueError(msg)
        if not args.csv.exists():
            _write(args.csv, {})
        return {"status": "unavailable", "observation_dates": len(existing)}
    return {"status": "updated", "observation_dates": snapshot(body, args.csv)}


def main(argv: list[str] | None = None) -> int:
    """Import one observation response or fetch the daily project endpoint.

    Parameters
    ----------
    argv
        Command arguments; None reads the actual process arguments.

    Returns
    -------
    int
        Zero for a completed import or explicitly allowed missing data; one for refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--response", type=Path)
    source.add_argument("--url", default=SOURCE_URL)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--project-csv-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = _request(args)
        print(json.dumps(result, sort_keys=True))
    except (ValueError, OSError, http.client.HTTPException) as error:
        print(f"downloads: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
