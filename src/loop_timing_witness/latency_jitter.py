# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — adjacent-cycle latency jitter

"""Measure changes between complete, consecutive post-warm-up latency samples."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .run_analysis import distribution

if TYPE_CHECKING:
    from collections.abc import Iterator

JITTER_METHOD = "absolute_cycle_to_cycle_latency_change.v1"


def jitter_pairs(rows: list[dict[str, int | str]]) -> Iterator[dict[str, int | str]]:
    """Yield auditable changes between adjacent cycles of the same interval.

    Parameters
    ----------
    rows
        Validated same-cycle interval rows in ascending cycle order, with
        warm-up already excluded. Each interval occurs at most once per cycle.

    Yields
    ------
    dict[str, int | str]
        Both cycle numbers and latencies, their signed difference and its
        absolute value in fabric ticks. Gaps never contribute a pair.
    """
    previous: dict[str, tuple[int, int]] = {}
    for row in rows:
        name = str(row["interval"])
        cycle, ticks = int(row["cycle"]), int(row["ticks"])
        earlier = previous.get(name)
        if earlier is not None and cycle == earlier[0] + 1:
            delta = ticks - earlier[1]
            yield {
                "interval": name,
                "previous_cycle": earlier[0],
                "cycle": cycle,
                "previous_ticks": earlier[1],
                "ticks": ticks,
                "delta_ticks": delta,
                "absolute_delta_ticks": abs(delta),
            }
        previous[name] = (cycle, ticks)


def summarise_jitter(
    rows: list[dict[str, int | str]],
    names: list[str],
    analysed_cycles: int,
    duration_ticks: int,
) -> dict[str, dict[str, int | float | str | None]]:
    """Report adjacent-cycle distributions separately from latency spread.

    Parameters
    ----------
    rows
        Validated periodic interval rows after warm-up, in cycle order.
    names
        Periodic interval names, including intervals with no observations.
    analysed_cycles
        Declared post-warm-up cycles; at most one fewer pair is possible.
    duration_ticks
        Observation span shared with the event report.

    Returns
    -------
    dict[str, dict[str, int | float | str | None]]
        Type-7 absolute-change distributions, pair coverage and duration.
        Peak-to-peak is maximum minus minimum latency, requires two latency
        observations and does not substitute for the adjacent-pair metric.
        Zero pairs are unavailable; incomplete nonempty coverage is partial.
    """
    latencies: dict[str, list[int]] = {name: [] for name in names}
    changes: dict[str, list[int]] = {name: [] for name in names}
    for row in rows:
        latencies[str(row["interval"])].append(int(row["ticks"]))
    for pair in jitter_pairs(rows):
        changes[str(pair["interval"])].append(int(pair["absolute_delta_ticks"]))
    expected = max(0, analysed_cycles - 1)
    result: dict[str, dict[str, int | float | str | None]] = {}
    for name in names:
        samples = latencies[name]
        count = len(changes[name])
        result[name] = {
            **distribution(changes[name]),
            "status": "unavailable"
            if not count
            else "available"
            if count == expected
            else "partial",
            "latency_sample_count": len(samples),
            "expected_pair_count": expected,
            "missing_pair_count": expected - count,
            "pair_coverage_fraction": count / expected if expected else None,
            "duration_ticks": duration_ticks,
            "peak_to_peak_ticks": max(samples) - min(samples) if len(samples) > 1 else None,
        }
    return result
