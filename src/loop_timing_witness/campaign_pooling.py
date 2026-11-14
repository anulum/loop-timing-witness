# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign pooling and spread

"""Pool the raw samples of valid repeats and state the spread of per-repeat statistics."""

from __future__ import annotations

from typing import Any, Final

from .latency_jitter import JITTER_METHOD, jitter_pairs
from .run_analysis import distribution

SPREAD_STATISTICS: Final = ("median_ticks", "p95_ticks", "p99_ticks", "p999_ticks", "maximum_ticks")
MAX_POOLED_TICKS: Final = 2**64 - 1
"""Longest pooled duration a report holds: the range of one 64-bit tick counter."""

Analysed = tuple[dict[str, Any], list[dict[str, int | str]]]
"""One analysed repeat: its run report and its per-cycle interval rows."""


def _pooled_samples(
    valid: list[Analysed], names: list[str]
) -> tuple[dict[str, list[int]], dict[str, list[int]], int]:
    """Concatenate every valid repeat's latencies and within-run jitter changes.

    Parameters
    ----------
    valid
        Run reports and interval rows of valid repeats.
    names
        Periodic interval names shared by every repeat.

    Returns
    -------
    tuple
        Latency samples and absolute adjacent-cycle changes by interval, and the number of
        adjacent-cycle pairs the repeats could have produced.
    """
    latencies: dict[str, list[int]] = {name: [] for name in names}
    changes: dict[str, list[int]] = {name: [] for name in names}
    expected_pairs = 0
    for report, rows in valid:
        for row in rows:
            latencies[str(row["interval"])].append(int(row["ticks"]))
        for pair in jitter_pairs(rows):
            changes[str(pair["interval"])].append(int(pair["absolute_delta_ticks"]))
        expected_pairs += max(0, report["events"]["cycle_count"] - 1)
    return latencies, changes, expected_pairs


def _pooled_jitter(
    changes: dict[str, list[int]], expected_pairs: int, duration: int
) -> dict[str, Any]:
    """Return the pooled jitter distribution and pair accounting of every interval.

    Parameters
    ----------
    changes
        Absolute adjacent-cycle changes by interval, in interval order.
    expected_pairs
        Pairs the valid repeats could have produced.
    duration
        Summed observation span of the valid repeats.

    Returns
    -------
    dict[str, Any]
        Per interval: distribution, status, expected and missing pairs, coverage and span.
    """
    jitter: dict[str, Any] = {}
    for name, values in changes.items():
        count = len(values)
        jitter[name] = {
            **distribution(values),
            "status": "unavailable"
            if not count
            else "available"
            if count == expected_pairs
            else "partial",
            "expected_pair_count": expected_pairs,
            "missing_pair_count": expected_pairs - count,
            "pair_coverage_fraction": count / expected_pairs if expected_pairs else None,
            "duration_ticks": duration,
        }
    return jitter


def _pooled_control(valid: list[Analysed]) -> dict[str, Any] | None:
    """Sum the deadline counts of valid CONTROL repeats.

    Parameters
    ----------
    valid
        Run reports and interval rows of valid repeats.

    Returns
    -------
    dict[str, Any] | None
        Observed deadlines, misses and miss rate, or ``None`` without CONTROL repeats.
    """
    controls = [report["events"]["control"] for report, _ in valid]
    if not controls or controls[0] is None:
        return None
    observed = sum(item["observed_deadlines"] for item in controls)
    misses = sum(item["deadline_misses"] for item in controls)
    return {
        "observed_deadlines": observed,
        "deadline_misses": misses,
        "deadline_miss_rate": misses / observed if observed else None,
    }


def pooled(valid: list[Analysed], names: list[str]) -> dict[str, Any]:
    """Pool raw latency samples and within-run jitter pairs of valid repeats.

    Parameters
    ----------
    valid
        Run reports and interval rows of valid repeats.
    names
        Periodic interval names shared by every repeat.

    Returns
    -------
    dict[str, Any]
        Type-7 distributions over the concatenated samples, summed duration,
        cycle and pair accounting, and summed deadline counts.

    Raises
    ------
    ValueError
        If the summed duration exceeds the 64-bit tick range. Summed cycle
        and pair counts cannot: each valid repeat has one anchor event in each
        of at most 2**32 analysed cycles.
    """
    latencies, changes, expected_pairs = _pooled_samples(valid, names)
    duration = sum(report["events"]["duration_ticks"] for report, _ in valid)
    if duration > MAX_POOLED_TICKS:
        message = "pooled duration exceeds the 64-bit tick range"
        raise ValueError(message)
    return {
        "repeat_count": len(valid),
        "run_ids": [report["run_id"] for report, _ in valid],
        "cycle_count": sum(report["events"]["cycle_count"] for report, _ in valid),
        "duration_ticks": duration,
        "intervals": {
            name: {**distribution(latencies[name]), "duration_ticks": duration} for name in names
        },
        "jitter_method": JITTER_METHOD,
        "jitter": _pooled_jitter(changes, expected_pairs, duration),
        "control": _pooled_control(valid),
    }


def spread(valid: list[Analysed], names: list[str], metric: str) -> dict[str, Any]:
    """State the range of each per-repeat statistic across valid repeats.

    Parameters
    ----------
    valid
        Run reports of valid repeats.
    names
        Periodic interval names.
    metric
        ``intervals`` for latency or ``jitter`` for adjacent-cycle change.

    Returns
    -------
    dict[str, Any]
        Minimum, maximum and range of each statistic. A statistic that any
        valid repeat could not compute, or with no valid repeat, is null.
    """
    result: dict[str, Any] = {}
    for name in names:
        result[name] = {}
        for statistic in SPREAD_STATISTICS:
            values = [report["events"][metric][name][statistic] for report, _ in valid]
            if not values or any(value is None for value in values):
                result[name][statistic] = {"minimum": None, "maximum": None, "range": None}
            else:
                result[name][statistic] = {
                    "minimum": min(values),
                    "maximum": max(values),
                    "range": max(values) - min(values),
                }
    return result
