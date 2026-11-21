# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fabric timebase against a pulse-per-second reference

"""Check the pulse-per-second fit and keep the corpus that the Rust analysis must reproduce.

The corpus holds edge series with no, one, two and many edges, a skipped edge, a counter that
runs fast with deterministic jitter, and an edge of another reference kind, each with Python's
result. The native crate's unit tests read the same committed file.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.event_stream import ReferenceEdge
from loop_timing_witness.reference_timebase import reference_timebase

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-reference-cases.json"
CLOCK_HZ: Final = 100_000_000


def _pulses(count: int, rate: int, jitter: int = 0, skip: int | None = None) -> list[ReferenceEdge]:
    """Return a deterministic pulse-per-second edge series.

    Parameters
    ----------
    count
        Number of sequence numbers covered, including a skipped one.
    rate
        Counter ticks per reference second.
    jitter
        Bound of a deterministic offset in ticks added to each edge.
    skip
        Sequence number left out, as an edge the fabric did not record.

    Returns
    -------
    list[ReferenceEdge]
        Edges from counter value 1,000 on, in capture order.
    """
    return [
        ReferenceEdge(
            "PPS", second, 1000 + second * rate + (second * 7919) % (2 * jitter + 1) - jitter
        )
        for second in range(count)
        if second != skip
    ]


def _cases() -> dict[str, list[ReferenceEdge]]:
    """Return the named edge series of the corpus.

    Returns
    -------
    dict[str, list[ReferenceEdge]]
        Edge series by case name.
    """
    return {
        "no edges": [],
        "one edge": _pulses(1, CLOCK_HZ),
        "two edges": _pulses(2, CLOCK_HZ + 7),
        "exact fast counter": _pulses(60, CLOCK_HZ + 50),
        "skipped edge": _pulses(10, CLOCK_HZ, skip=4),
        "jitter": _pulses(3600, CLOCK_HZ - 1234, jitter=40),
        "other reference": [ReferenceEdge("OTHER", 0, 5), *_pulses(3, CLOCK_HZ)],
        "ringing edge": _ringing(),
        "skipped reference pulse": _skipped_pulse(),
        "slow edge off a second": [
            *_pulses(3, CLOCK_HZ),
            ReferenceEdge("PPS", 3, 1000 + 3 * CLOCK_HZ + 200_000),
        ],
    }


def _ringing() -> list[ReferenceEdge]:
    """Return five reference seconds with a second rising edge 300 ticks after the third.

    The fabric counts every synchronised rising edge, so the extra edge takes a sequence number.

    Returns
    -------
    list[ReferenceEdge]
        Edges at seconds 0, 1, 2, the ringing edge, then seconds 3 and 4.
    """
    edges = _pulses(3, CLOCK_HZ)
    edges.append(ReferenceEdge("PPS", 3, edges[-1].ticks + 300))
    edges.extend(
        ReferenceEdge("PPS", 4 + second, 1000 + (3 + second) * CLOCK_HZ) for second in range(2)
    )
    return edges


def _skipped_pulse() -> list[ReferenceEdge]:
    """Return a reference that sends no pulse at second 3: contiguous sequence numbers, a 2 s step.

    Returns
    -------
    list[ReferenceEdge]
        Edges at seconds 0, 1, 2, 4 and 5 with sequence numbers 0 to 4.
    """
    return [
        ReferenceEdge("PPS", sequence, 1000 + second * (CLOCK_HZ + 20))
        for sequence, second in enumerate((0, 1, 2, 4, 5))
    ]


def corpus() -> dict[str, Any]:
    """Build the complete reference-timebase corpus.

    Returns
    -------
    dict[str, Any]
        Edge series as ``[name, sequence, ticks]`` with Python's block for each.
    """
    return {
        "schema": "loop-timing-witness.control-reference-cases.v1",
        "clock_hz": CLOCK_HZ,
        "cases": [
            {
                "name": name,
                "edges": [[edge.name, edge.sequence, edge.ticks] for edge in edges],
                "result": reference_timebase(edges, CLOCK_HZ),
            }
            for name, edges in _cases().items()
        ],
    }


def test_committed_corpus_equals_python_results() -> None:
    """The committed corpus is exactly what the Python fit gives."""
    text = json.dumps(corpus(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert CORPUS.read_text(encoding="utf-8") == text + "\n"
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_no_pulse_gives_no_block() -> None:
    """A run without pulse-per-second edges has no reference timebase."""
    assert reference_timebase([], CLOCK_HZ) is None
    assert reference_timebase([ReferenceEdge("OTHER", 0, 5)], CLOCK_HZ) is None


def test_one_edge_counts_without_a_fit() -> None:
    """One edge is counted; the fit values stay empty."""
    block = reference_timebase([ReferenceEdge("PPS", 3, 900)], CLOCK_HZ)
    assert block == {
        "event": "PPS",
        "edges": 1,
        "first_sequence": 3,
        "last_sequence": 3,
        "missing_edges": 0,
        "rejected_edges": 0,
        "seconds": 0,
        "ticks_per_second": None,
        "scale_error_ppm": None,
        "scale_standard_error_ppm": None,
        "residual_rms_ticks": None,
        "max_abs_residual_ticks": None,
    }


def test_two_edges_give_a_slope_with_the_quantization_uncertainty() -> None:
    """Two edges determine the slope exactly; its uncertainty is the counter's resolution.

    With one tick of uniform error per edge, variance 1/12, and seconds 0 and 1 (spread 1/2), the
    slope's standard uncertainty is sqrt(1/6) tick per second.
    """
    block = reference_timebase(_pulses(2, CLOCK_HZ + 7), CLOCK_HZ)
    assert block is not None
    assert block["ticks_per_second"] == CLOCK_HZ + 7
    assert block["scale_error_ppm"] == pytest.approx(0.07)
    assert block["max_abs_residual_ticks"] == 0.0
    assert block["scale_standard_error_ppm"] == pytest.approx(math.sqrt(1 / 6) / CLOCK_HZ * 1e6)
    assert block["residual_rms_ticks"] is None
    assert block["seconds"] == 1


def test_an_exact_fast_counter_keeps_the_quantization_floor() -> None:
    """A counter 50 ticks per second fast is half a part per million fast, without scatter.

    The residuals are zero, so the standard uncertainty is the quantization floor, not zero:
    sqrt((1/12) / S) with S the spread of seconds 0 to 59.
    """
    block = reference_timebase(_pulses(60, CLOCK_HZ + 50), CLOCK_HZ)
    assert block is not None
    assert block["ticks_per_second"] == CLOCK_HZ + 50
    assert block["scale_error_ppm"] == pytest.approx(0.5)
    spread = sum((second - 29.5) ** 2 for second in range(60))
    assert block["scale_standard_error_ppm"] == pytest.approx(
        math.sqrt(1 / 12 / spread) / CLOCK_HZ * 1e6
    )
    assert block["residual_rms_ticks"] == 0.0
    assert (block["missing_edges"], block["rejected_edges"], block["seconds"]) == (0, 0, 59)


def test_a_ringing_edge_is_rejected_and_the_seconds_stay_whole() -> None:
    """A second rising edge 3 microseconds after a pulse takes a sequence number but no second."""
    block = reference_timebase(_ringing(), CLOCK_HZ)
    assert block is not None
    assert (block["edges"], block["rejected_edges"], block["seconds"]) == (6, 1, 4)
    assert (block["first_sequence"], block["last_sequence"], block["missing_edges"]) == (0, 5, 0)
    assert block["ticks_per_second"] == CLOCK_HZ
    assert block["max_abs_residual_ticks"] == 0.0


def test_a_pulse_the_reference_skipped_spans_two_seconds() -> None:
    """Without a pulse at second 3 the sequence is contiguous but the counter spans 5 seconds.

    Seconds from the sequence would put 2 s of ticks at 1 s and give a scale error near 20 %;
    seconds from the counter keep the 0.2 ppm the edges carry.
    """
    block = reference_timebase(_skipped_pulse(), CLOCK_HZ)
    assert block is not None
    assert block["seconds"] == 5
    assert block["last_sequence"] - block["first_sequence"] == 4
    assert (block["missing_edges"], block["rejected_edges"]) == (0, 0)
    assert block["ticks_per_second"] == pytest.approx(CLOCK_HZ + 20)
    assert block["scale_error_ppm"] == pytest.approx(0.2)


def test_an_edge_off_a_whole_second_is_rejected() -> None:
    """An edge 2 ms past a whole second, beyond one part in a thousand, is left out of the fit."""
    edges = [*_pulses(3, CLOCK_HZ), ReferenceEdge("PPS", 3, 1000 + 3 * CLOCK_HZ + 200_000)]
    block = reference_timebase(edges, CLOCK_HZ)
    assert block is not None
    assert (block["rejected_edges"], block["seconds"]) == (1, 2)
    assert block["ticks_per_second"] == CLOCK_HZ


def test_an_edge_at_or_before_its_predecessor_is_rejected() -> None:
    """A counter value that does not advance cannot be a later second."""
    edges = [
        ReferenceEdge("PPS", 0, 5_000),
        ReferenceEdge("PPS", 1, 5_000),
        ReferenceEdge("PPS", 2, 4_000),
    ]
    block = reference_timebase(edges, CLOCK_HZ)
    assert block is not None
    assert (block["rejected_edges"], block["seconds"]) == (2, 0)
    assert block["ticks_per_second"] is None


def test_a_skipped_edge_is_counted_and_spans_its_second() -> None:
    """A gap in the sequence numbers is a missing edge, and the fit uses the real seconds."""
    block = reference_timebase(_pulses(10, CLOCK_HZ, skip=4), CLOCK_HZ)
    assert block is not None
    assert (block["edges"], block["first_sequence"], block["last_sequence"]) == (9, 0, 9)
    assert block["missing_edges"] == 1
    assert block["ticks_per_second"] == CLOCK_HZ


def test_jitter_widens_the_standard_error_but_not_the_estimate() -> None:
    """Bounded symmetric jitter leaves the slope near the true rate with a positive error bar."""
    block = reference_timebase(_pulses(3600, CLOCK_HZ - 1234, jitter=40), CLOCK_HZ)
    assert block is not None
    assert block["scale_error_ppm"] == pytest.approx(-12.34, abs=0.01)
    assert 0.0 < block["scale_standard_error_ppm"] < 0.01
    assert 0.0 < block["residual_rms_ticks"] <= block["max_abs_residual_ticks"] <= 80.0
    standard_error = block["scale_standard_error_ppm"]
    assert abs(block["scale_error_ppm"] + 12.34) < 5 * standard_error + 1e-9
    assert math.isfinite(standard_error)
