# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tail quantile intervals of a published run report

"""Bound a published report's tail quantiles with block-bootstrap confidence intervals.

The command reads a report directory that the run analysis published, takes each periodic
interval's samples from ``cycle_intervals.csv`` in cycle order and gives the p95, p99 and p99.9
intervals of :func:`loop_timing_witness.tail_statistics.tail_quantiles`. The samples must be the
report's own: each interval needs as many rows as its distribution counts and the same Type-7
quantiles, and the result names both files by SHA-256. The bootstrap costs about a thousand
sorts of the series, which is why the run analysis leaves it to this separate step.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Final

from loop_timing_witness.manifest_io import parse_bounded_json_object, read_regular_bytes
from loop_timing_witness.tail_statistics import CONFIDENCE, RESAMPLES, SEED, tail_quantiles

RESULT_SCHEMA: Final = "loop-timing-witness.tail-intervals.v1"
"""Schema identifier of a tail-interval result."""

COLUMNS: Final = ["run_id", "evidence_status", "cycle", "interval", "ticks"]
"""Header of the report's per-cycle interval table."""


def _samples(table: bytes, run_id: str, evidence: object) -> dict[str, list[int]]:
    """Read the per-cycle interval table of one run.

    Parameters
    ----------
    table
        ``cycle_intervals.csv`` bytes.
    run_id
        Run identifier every row must carry.
    evidence
        Evidence status every row must carry.

    Returns
    -------
    dict[str, list[int]]
        Tick samples per interval, in table order.

    Raises
    ------
    ValueError
        If the header differs, a row belongs to another run or a count is not a decimal integer.
    """
    reader = csv.reader(io.StringIO(table.decode("utf-8"), newline=""), strict=True)
    if next(reader, None) != COLUMNS:
        message = "cycle_intervals.csv header differs from the report table"
        raise ValueError(message)
    samples: dict[str, list[int]] = {}
    for row in reader:
        if len(row) != len(COLUMNS) or row[:2] != [run_id, evidence] or not row[4].isdigit():
            message = "cycle_intervals.csv row does not belong to the report"
            raise ValueError(message)
        samples.setdefault(row[3], []).append(int(row[4]))
    return samples


def tail_intervals(directory: Path) -> dict[str, Any]:
    """Compute the tail quantile intervals of every periodic interval of a report.

    Parameters
    ----------
    directory
        Report directory with ``report.json`` and ``cycle_intervals.csv``.

    Returns
    -------
    dict[str, Any]
        Schema, run identity, evidence status, digests of both files, method parameters and the
        tail quantiles per interval.

    Raises
    ------
    ValueError
        If the report or table is malformed, or the samples differ from the report's
        distributions.
    """
    report_bytes = read_regular_bytes(directory / "report.json")
    table = read_regular_bytes(directory / "cycle_intervals.csv")
    report = parse_bounded_json_object(report_bytes, str(directory / "report.json"))
    distributions = report.get("events", {}).get("intervals")
    if not isinstance(distributions, dict) or not isinstance(report.get("run_id"), str):
        message = "report has no interval distributions"
        raise ValueError(message)
    samples = _samples(table, report["run_id"], report.get("evidence_status"))
    intervals: dict[str, Any] = {}
    for name, values in sorted(samples.items()):
        distribution = distributions.get(name)
        result = tail_quantiles(values)
        quantiles = result["quantiles"]
        if (
            not isinstance(distribution, dict)
            or distribution.get("sample_count") != len(values)
            or any(distribution.get(key) != quantiles[key]["estimate"] for key in quantiles)
        ):
            message = f"cycle_intervals.csv samples of {name} differ from the report"
            raise ValueError(message)
        intervals[name] = result
    return {
        "schema": RESULT_SCHEMA,
        "run_id": report["run_id"],
        "evidence_status": report.get("evidence_status"),
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "cycle_intervals_sha256": hashlib.sha256(table).hexdigest(),
        "method": "moving_block_bootstrap_percentile",
        "resamples": RESAMPLES,
        "confidence": CONFIDENCE,
        "seed": SEED,
        "intervals": intervals,
    }


def main(argv: list[str] | None = None) -> int:
    """Print the tail quantile intervals of one report directory as JSON.

    Parameters
    ----------
    argv
        One argument, the report directory; ``None`` reads ``sys.argv``.

    Returns
    -------
    int
        0 after printing the result, 2 for a refused report or wrong usage.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print(
            "usage: python -m loop_timing_witness.tail_intervals REPORT_DIRECTORY", file=sys.stderr
        )
        return 2
    try:
        result = tail_intervals(Path(arguments[0]))
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as error:
        print(f"tail intervals refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
