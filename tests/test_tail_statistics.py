# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tail quantile intervals and weakly-hard deadline metrics

"""Check the tail statistics and keep the corpus that the Rust analysis must reproduce.

The corpus holds interval series at every reportability level of the minimum-sample rule, with
serially dependent bursts so that blocks matter, and miss sequences for the weakly-hard windows,
each with Python's result. The native crate's unit tests read the same committed file.
"""

from __future__ import annotations

import json
from typing import Any, Final

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.tail_statistics import (
    QUANTILES,
    RESAMPLES,
    SplitMix64,
    block_length,
    tail_quantiles,
    type7,
    weakly_hard,
)

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-tail-cases.json"


def _series(count: int, period: int) -> list[int]:
    """Return a deterministic latency series with serially dependent bursts.

    Parameters
    ----------
    count
        Number of samples.
    period
        Cycles between the starts of two 20-cycle bursts.

    Returns
    -------
    list[int]
        Ticks: a base latency, a spread from a multiplicative sequence and a burst offset that
        holds for 20 consecutive cycles.
    """
    return [
        1000 + (index * 7919) % 97 + (400 if index % period < 20 else 0) for index in range(count)
    ]


def _misses(count: int) -> list[bool]:
    """Return a deterministic miss sequence with isolated misses and one cluster.

    Parameters
    ----------
    count
        Number of observed deadlines.

    Returns
    -------
    list[bool]
        A miss every 37th deadline and a cluster of five misses at deadlines 600 to 604.
    """
    return [index % 37 == 0 or 600 <= index < 605 for index in range(count)]


def corpus() -> dict[str, Any]:
    """Build the complete tail-statistics corpus.

    Returns
    -------
    dict[str, Any]
        Interval series with Python's tail quantiles and miss sequences with Python's metrics.
    """
    series = {
        "empty": [],
        "one sample": [7],
        "below the p95 rule": _series(199, 50),
        "p95 reportable": _series(200, 50),
        "p99 reportable": _series(1000, 300),
        "p999 reportable": _series(10000, 2500),
    }
    misses = {"none": [], "isolated and clustered": _misses(1200), "all missed": [True] * 4}
    return {
        "schema": "loop-timing-witness.control-tail-cases.v1",
        "tail_cases": [
            {"name": name, "values": values, "result": tail_quantiles(values)}
            for name, values in series.items()
        ],
        "weakly_hard_cases": [
            {"name": name, "misses": flags, "result": weakly_hard(flags)}
            for name, flags in misses.items()
        ],
    }


def test_committed_corpus_equals_python_results() -> None:
    """The committed corpus is exactly what the Python tail statistics give."""
    text = json.dumps(corpus(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert CORPUS.read_text(encoding="utf-8") == text + "\n"


def test_splitmix64_reproduces_the_published_sequence() -> None:
    """The generator gives SplitMix64's first outputs from seed zero."""
    generator = SplitMix64(0)
    assert [generator.next() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]


def test_block_length_is_the_integer_fourth_root_ceiling() -> None:
    """Block lengths are the smallest integers whose fourth power reaches the count."""
    assert [block_length(count) for count in (1, 2, 16, 17, 81, 82, 64000)] == [
        1,
        2,
        2,
        3,
        3,
        4,
        16,
    ]


@pytest.mark.parametrize(
    ("count", "reportable"),
    [
        (0, [False, False, False]),
        (199, [False, False, False]),
        (200, [True, False, False]),
        (999, [True, False, False]),
        (1000, [True, True, False]),
        (9999, [True, True, False]),
        (10000, [True, True, True]),
    ],
)
def test_minimum_sample_rule(count: int, reportable: list[bool]) -> None:
    """A quantile is reportable with ten expected samples beyond it, and only then has bounds.

    Parameters
    ----------
    count
        Samples in the series.
    reportable
        Expected reportability of p95, p99 and p99.9.
    """
    result = tail_quantiles(_series(count, 250))
    quantiles = result["quantiles"]
    assert isinstance(quantiles, dict)
    assert [quantiles[name]["reportable"] for name, _ in QUANTILES] == reportable
    for (name, _), flag in zip(QUANTILES, reportable, strict=True):
        assert (quantiles[name]["lower"] is not None) == flag
        assert (quantiles[name]["upper"] is not None) == flag
    assert result["resamples"] == (RESAMPLES if any(reportable) else 0)


def test_estimates_match_the_report_distribution_and_lie_in_their_intervals() -> None:
    """Each estimate is the Type-7 quantile and lies inside its percentile interval."""
    values = _series(1000, 300)
    result = tail_quantiles(values)
    quantiles = result["quantiles"]
    assert isinstance(quantiles, dict)
    ordered = sorted(values)
    for name, thousandths in QUANTILES:
        entry = quantiles[name]
        assert entry["estimate"] == type7(ordered, thousandths / 1000)
        if entry["reportable"]:
            assert entry["lower"] <= entry["estimate"] <= entry["upper"]
    assert result["block_length"] == 6


def test_dependent_bursts_widen_the_interval_over_shuffled_data() -> None:
    """Blocks keep the 20-cycle bursts together, so p95 is less certain than for scattered bursts.

    The same values read with a stride of seven cycles, which separates the samples of every burst,
    give a much narrower p95 interval: resamples then hold close to the true share of burst samples,
    while blocks of whole bursts make that share vary between resamples.
    """
    bursty = _series(1000, 300)
    scattered = [bursty[(index * 7) % 1000] for index in range(1000)]
    width = []
    for values in (bursty, scattered):
        entry = tail_quantiles(values)["quantiles"]
        assert isinstance(entry, dict)
        width.append(entry["p95_ticks"]["upper"] - entry["p95_ticks"]["lower"])
    assert width[0] > 5 * width[1]


def test_weakly_hard_windows_count_the_largest_miss_cluster() -> None:
    """The window maxima and the longest miss run of a short sequence."""
    flags = [False, True, True, False, True, False, False, False, False, False, True]
    assert weakly_hard(flags) == {
        "observed_deadlines": 11,
        "longest_miss_run": 2,
        "maximum_misses_in_window": {
            "2": 2,
            "3": 2,
            "5": 3,
            "10": 4,
            "20": None,
            "50": None,
            "100": None,
            "1000": None,
        },
    }
    clustered = weakly_hard(_misses(1200))
    assert clustered["longest_miss_run"] == 5
    windows = clustered["maximum_misses_in_window"]
    assert isinstance(windows, dict)
    assert windows["5"] == 5
    assert windows["1000"] == 33
