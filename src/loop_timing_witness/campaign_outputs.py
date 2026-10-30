# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign report files

"""Write a repeat campaign report as one atomic directory of JSON and CSV files."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .campaign_analysis import SPREAD_STATISTICS
from .manifest_io import canonical_json_bytes
from .report_outputs import csv_table_bytes
from .report_publication import publish_report_directory

if TYPE_CHECKING:
    from pathlib import Path

_DISTRIBUTION_COLUMNS: Final = (
    "sample_count",
    "median_ticks",
    "p95_ticks",
    "p99_ticks",
    "p999_ticks",
    "maximum_ticks",
)
_METRICS: Final = (("latency", "intervals"), ("jitter", "jitter"))


def _repeat_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten per-repeat latency and jitter distributions.

    Parameters
    ----------
    report
        Repeat campaign report.

    Returns
    -------
    list[dict[str, Any]]
        One row per repeat, metric and interval; a refused repeat has one row
        with its status and no statistics.
    """
    rows: list[dict[str, Any]] = []
    for entry in report["repeats"]:
        identity = {
            "campaign_id": report["campaign_id"],
            "evidence_status": report["evidence_status"],
            "repeat_index": entry["repeat_index"],
            "run_id": entry["run_id"],
            "status": entry["status"],
        }
        if entry["intervals"] is None:
            rows.append(identity)
            continue
        for metric, key in _METRICS:
            rows.extend(
                {
                    **identity,
                    "metric": metric,
                    "interval": name,
                    **statistics,
                    "duration_ticks": entry["duration_ticks"],
                }
                for name, statistics in sorted(entry[key].items())
            )
    return rows


def _pooled_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten pooled latency and jitter distributions.

    Parameters
    ----------
    report
        Repeat campaign report.

    Returns
    -------
    list[dict[str, Any]]
        One row per metric and periodic interval.
    """
    pooled = report["pooled"]
    return [
        {
            "campaign_id": report["campaign_id"],
            "evidence_status": report["evidence_status"],
            "metric": metric,
            "interval": name,
            "repeat_count": pooled["repeat_count"],
            **statistics,
        }
        for metric, key in _METRICS
        for name, statistics in sorted(pooled[key].items())
    ]


def _spread_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the range of each per-repeat statistic.

    Parameters
    ----------
    report
        Repeat campaign report.

    Returns
    -------
    list[dict[str, Any]]
        One row per metric, interval and statistic.
    """
    return [
        {
            "campaign_id": report["campaign_id"],
            "evidence_status": report["evidence_status"],
            "metric": metric,
            "interval": name,
            "statistic": statistic,
            **statistics[statistic],
        }
        for metric, key in _METRICS
        for name, statistics in sorted(report["spread"][key].items())
        for statistic in SPREAD_STATISTICS
    ]


def write_campaign_report(output_directory: Path, report: dict[str, Any]) -> None:
    """Publish the campaign report directory only after every file is written.

    Parameters
    ----------
    output_directory
        New report directory; it must not exist and its parent must exist.
    report
        Complete repeat campaign report.

    Raises
    ------
    FileExistsError
        If the output path already exists.
    OSError
        If the parent is missing, atomic publication is unavailable or a
        file cannot be written.
    """
    identity = ("campaign_id", "evidence_status")
    files = {
        "campaign_report.json": canonical_json_bytes(report),
        "repeat_summary.csv": csv_table_bytes(
            (
                *identity,
                "repeat_index",
                "run_id",
                "status",
                "metric",
                "interval",
                *_DISTRIBUTION_COLUMNS,
                "duration_ticks",
            ),
            _repeat_rows(report),
        ),
        "pooled_summary.csv": csv_table_bytes(
            (
                *identity,
                "metric",
                "interval",
                "repeat_count",
                *_DISTRIBUTION_COLUMNS,
                "expected_pair_count",
                "missing_pair_count",
                "pair_coverage_fraction",
                "duration_ticks",
            ),
            _pooled_rows(report),
        ),
        "repeat_spread.csv": csv_table_bytes(
            (*identity, "metric", "interval", "statistic", "minimum", "maximum", "range"),
            _spread_rows(report),
        ),
    }
    publish_report_directory(output_directory, files)
