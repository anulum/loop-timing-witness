# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tail quantile intervals and weakly-hard deadline metrics

"""Confidence intervals for tail latency quantiles and consecutive deadline-miss metrics.

Successive control cycles are not independent: a cache, scheduler or interrupt state can hold over
many cycles. The moving-block bootstrap (Künsch, 1989) keeps that dependence inside blocks of
consecutive samples: each resample joins blocks drawn uniformly from all ``n - b + 1`` starting
positions and is cut to ``n`` samples, and the percentile interval of the resampled quantiles bounds
the quantile. The block length is the integer ceiling of the fourth root of ``n``: Hall, Horowitz
and Jing (1995) derive that order for the mean-squared-error optimal block length when the
bootstrap estimates a one-sided distribution function, which each bound of a percentile interval is.
Resamples come from SplitMix64 (Steele, Lea and Flood, 2014) with a fixed seed, so the Rust
analysis reproduces every interval exactly.

A quantile ``p`` is reportable only when at least ``TAIL_SAMPLES`` samples are expected beyond it,
``n (1 - p) >= TAIL_SAMPLES``: 200 samples for p95, 1,000 for p99 and 10,000 for p99.9. Below that
the estimate stays, without an interval, and is marked as not reportable.

The weakly-hard metrics follow the ``(m, K)`` model of Bernat, Burns and Llamosí (2001): a loop
meets ``(m, K)`` when no ``K`` consecutive deadlines hold more than ``m`` misses. For each window
length ``K`` the largest number of misses in any window of ``K`` consecutive observed deadlines is
reported, so every ``(m, K)`` constraint with a listed ``K`` can be read off; the longest run of
consecutive misses is the ``m = K - 1`` boundary.
"""

from __future__ import annotations

from math import ceil, floor
from typing import Any, Final

SEED: Final = 0x4C54572D5441494C
"""SplitMix64 seed of every resampling."""

RESAMPLES: Final = 1000
"""Bootstrap resamples per distribution."""

CONFIDENCE: Final = 0.95
"""Coverage of the percentile intervals."""

TAIL_SAMPLES: Final = 10
"""Expected samples beyond a quantile that make it reportable."""

QUANTILES: Final = (("p95_ticks", 950), ("p99_ticks", 990), ("p999_ticks", 999))
"""Reported quantiles, by report name and probability in thousandths."""

WINDOWS: Final = (2, 3, 5, 10, 20, 50, 100, 1000)
"""Window lengths ``K`` of the weakly-hard metrics, in consecutive deadlines."""

_MASK: Final = (1 << 64) - 1


class SplitMix64:
    """The SplitMix64 generator, the same 64-bit sequence as the Rust analysis.

    Parameters
    ----------
    seed
        Initial 64-bit state.
    """

    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK

    def next(self) -> int:
        """Return the next 64-bit output.

        Returns
        -------
        int
            Value in ``[0, 2**64)``.
        """
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK
        return value ^ (value >> 31)


def type7(ordered: list[int] | list[float], probability: float) -> float:
    """Return the Type-7 quantile of sorted data, as the report's distributions use.

    Parameters
    ----------
    ordered
        Non-empty ascending values.
    probability
        Quantile probability in ``[0, 1]``.

    Returns
    -------
    float
        Linear interpolation at ``(n - 1) * probability`` on zero-based data.
    """
    position = (len(ordered) - 1) * probability
    low = floor(position)
    high = ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def block_length(count: int) -> int:
    """Return the smallest block length whose fourth power is at least the sample count.

    Parameters
    ----------
    count
        Positive sample count.

    Returns
    -------
    int
        Integer ceiling of the fourth root, computed without floating point.
    """
    length = 1
    while length**4 < count:
        length += 1
    return length


def _interpolate(ordered: list[int], position: float, offset: int) -> float:
    """Return the Type-7 value at a zero-based position of data whose first ``offset`` are omitted.

    Parameters
    ----------
    ordered
        Ascending values from rank ``offset`` on.
    position
        Zero-based position ``(n - 1) * p`` in the complete data.
    offset
        Number of lower values left out of ``ordered``.

    Returns
    -------
    float
        The same operations, in the same order, as :func:`type7` on the complete data.
    """
    low = floor(position)
    lower = ordered[low - offset]
    return lower + (ordered[ceil(position) - offset] - lower) * (position - low)


class _Resampler:
    """Exact order statistics of block resamples, from the samples above the 90th percentile.

    The order statistics the reported quantiles need lie in the top tenth of every resample in all
    but rare cases, so each resample collects only its samples above the series' 90th percentile,
    from per-position prefix counts, and sorts those. When a needed order statistic falls below
    them, the whole resample is sorted. Either way the result equals a full sort of the resample.

    Parameters
    ----------
    values
        Samples in cycle order.
    length
        Block length.
    """

    def __init__(self, values: list[int], length: int) -> None:
        self.values = values
        self.length = length
        self.count = len(values)
        threshold = sorted(values)[floor((self.count - 1) * 0.9)]
        self.above = [value for value in values if value > threshold]
        self.before = [0]
        for value in values:
            self.before.append(self.before[-1] + (value > threshold))

    def quantiles(self, starts: list[int], positions: list[float]) -> list[float]:
        """Return the Type-7 quantiles of one resample.

        Parameters
        ----------
        starts
            Block starts of the resample, in order; the last block is cut to the sample count.
        positions
            Zero-based quantile positions ``(n - 1) * p``.

        Returns
        -------
        list[float]
            One quantile per position.
        """
        ends = [start + self.length for start in starts]
        ends[-1] = starts[-1] + self.count - self.length * (len(starts) - 1)
        tail: list[int] = []
        for start, end in zip(starts, ends, strict=True):
            tail.extend(self.above[self.before[start] : self.before[end]])
        below = self.count - len(tail)
        if floor(min(positions)) >= below:
            tail.sort()
            return [_interpolate(tail, position, below) for position in positions]
        resample: list[int] = []
        for start, end in zip(starts, ends, strict=True):
            resample.extend(self.values[start:end])
        resample.sort()
        return [_interpolate(resample, position, 0) for position in positions]


def tail_quantiles(values: list[int]) -> dict[str, Any]:
    """Estimate the tail quantiles of one interval series with block-bootstrap intervals.

    Parameters
    ----------
    values
        Clock-tick samples in cycle order.

    Returns
    -------
    dict[str, Any]
        Sample count, block length, resamples and confidence, and for each tail quantile its
        Type-7 estimate, whether it is reportable and the interval bounds (``None`` when it is
        not reportable).
    """
    count = len(values)
    reportable = [
        name
        for name, thousandths in QUANTILES
        if count * (1000 - thousandths) >= TAIL_SAMPLES * 1000
    ]
    ordered = sorted(values)
    bounds: dict[str, tuple[float, float]] = {}
    length = block_length(count) if count else 0
    if reportable:
        generator = SplitMix64(SEED)
        starts = count - length + 1
        blocks = -(-count // length)
        resampler = _Resampler(values, length)
        positions = [
            (count - 1) * (thousandths / 1000)
            for name, thousandths in QUANTILES
            if name in reportable
        ]
        estimates: list[list[float]] = [[] for _ in reportable]
        for _ in range(RESAMPLES):
            drawn = [generator.next() % starts for _ in range(blocks)]
            for index, value in enumerate(resampler.quantiles(drawn, positions)):
                estimates[index].append(value)
        tail = (1 - CONFIDENCE) / 2
        for name, ranked in zip(reportable, estimates, strict=True):
            ranked.sort()
            bounds[name] = (type7(ranked, tail), type7(ranked, 1 - tail))
    return {
        "sample_count": count,
        "block_length": length,
        "resamples": RESAMPLES if bounds else 0,
        "confidence": CONFIDENCE,
        "quantiles": {
            name: {
                "estimate": type7(ordered, thousandths / 1000) if count else None,
                "reportable": name in reportable,
                "lower": bounds[name][0] if name in bounds else None,
                "upper": bounds[name][1] if name in bounds else None,
            }
            for name, thousandths in QUANTILES
        },
    }


def weakly_hard(misses: list[bool]) -> dict[str, object]:
    """Return the consecutive deadline-miss metrics of one run.

    Parameters
    ----------
    misses
        Whether each observed deadline was missed, in cycle order.

    Returns
    -------
    dict[str, object]
        Observed deadlines, the longest run of consecutive misses and, for each window length
        ``K`` of ``WINDOWS``, the largest number of misses in ``K`` consecutive deadlines
        (``None`` when the run has fewer deadlines than ``K``).
    """
    longest = run = 0
    for missed in misses:
        run = run + 1 if missed else 0
        longest = max(longest, run)
    windows: dict[str, int | None] = {}
    for window in WINDOWS:
        if window > len(misses):
            windows[str(window)] = None
            continue
        current = sum(misses[:window])
        largest = current
        for index in range(window, len(misses)):
            current += misses[index] - misses[index - window]
            largest = max(largest, current)
        windows[str(window)] = largest
    return {
        "observed_deadlines": len(misses),
        "longest_miss_run": longest,
        "maximum_misses_in_window": windows,
    }
