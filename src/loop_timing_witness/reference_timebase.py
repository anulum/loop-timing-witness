# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fabric timebase against a pulse-per-second reference

"""Fit the fabric counter against the edges of a pulse-per-second reference.

The first recorded edge anchors the reference. Each later edge is accepted when its counter
distance to the previous accepted edge is a whole, positive number of seconds at the declared
clock frequency, within one part in ``GLITCH_TOLERANCE`` of that distance; an edge that is not, such
as a second rising edge from a ringing input, is counted as rejected and left out. Each accepted
edge's second is the sum of those whole numbers, so a pulse the reference did not send leaves a
two-second step instead of shifting every later second, and the run's ``seconds`` exceed its
sequence span by the pulses the reference skipped. An ordinary least-squares line through the
accepted (second, counter value) pairs gives the counter's ticks per second; its scale error
against the declared clock is in parts per million. The slope's standard uncertainty uses the
residual variance, but never less than the counter's own quantization, a uniform error within one
tick, variance ``1/12`` tick squared, per edge, so two edges, or edges that fall on whole ticks,
still report the resolution the counter allows. The result describes the counter relative to the
reference: the reference's own error is not inferred and has to be added from the reference's
declaration. Every sum runs left to right in plain float arithmetic, the operation order of the Rust
analysis, so both give the same bits.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from loop_timing_witness.event_stream import ReferenceEdge

REFERENCE_EVENT: Final = "PPS"
"""The reference event whose edges are one second apart."""

PARTS_PER_MILLION: Final = 1_000_000.0
"""Scale of a relative error in parts per million."""

LINE_POINTS: Final = 2
"""Edges that determine a line; a residual variance needs one more."""

GLITCH_TOLERANCE: Final = 1000.0
"""An accepted edge lies within one part in this many of a whole number of seconds."""

QUANTIZATION_VARIANCE: Final = 1.0 / 12.0
"""Variance of one edge's counter value in ticks squared: a uniform error within one tick."""


def _total(values: Sequence[float]) -> float:
    """Sum floats left to right, without the compensated summation of :func:`sum`.

    Parameters
    ----------
    values
        Terms in order.

    Returns
    -------
    float
        The plain running sum.
    """
    total = 0.0
    for value in values:
        total += value
    return total


def _accepted(pulses: Sequence[ReferenceEdge], clock: float) -> tuple[list[float], list[float]]:
    """Return the seconds and counter offsets of the edges a whole second apart.

    Parameters
    ----------
    pulses
        Pulse-per-second edges in capture order, at least one.
    clock
        Declared counter frequency.

    Returns
    -------
    tuple[list[float], list[float]]
        Whole seconds and counter values of the accepted edges, both from the first edge.
    """
    first = pulses[0]
    seconds, ticks = [0.0], [0.0]
    previous = first.ticks
    for edge in pulses[1:]:
        elapsed = float(edge.ticks - previous)
        whole = math.floor(elapsed / clock + 0.5)
        if whole < 1 or abs(elapsed - whole * clock) * GLITCH_TOLERANCE > whole * clock:
            continue
        seconds.append(seconds[-1] + whole)
        ticks.append(float(edge.ticks - first.ticks))
        previous = edge.ticks
    return seconds, ticks


def reference_timebase(edges: Sequence[ReferenceEdge], clock_hz: int) -> dict[str, Any] | None:
    """Summarise the pulse-per-second edges of one run and fit the counter against them.

    Parameters
    ----------
    edges
        Reference edges in capture order, sequence numbers and counter values increasing.
    clock_hz
        Declared counter frequency.

    Returns
    -------
    dict[str, Any] | None
        ``None`` without pulse-per-second edges. Otherwise the edge count, first and last sequence
        numbers, the sequence numbers missing from the records, the edges rejected as off a whole
        second and the whole seconds the accepted edges span; with two or more accepted edges the
        fitted ticks per second, the scale error in parts per million with its standard
        uncertainty and the largest absolute residual; with three or more the root-mean-square
        residual. Fit values are ``None`` when they cannot be formed.
    """
    pulses = [edge for edge in edges if edge.name == REFERENCE_EVENT]
    if not pulses:
        return None
    count = len(pulses)
    first, last = pulses[0], pulses[-1]
    seconds, ticks = _accepted(pulses, float(clock_hz))
    accepted = len(seconds)
    block: dict[str, Any] = {
        "event": REFERENCE_EVENT,
        "edges": count,
        "first_sequence": first.sequence,
        "last_sequence": last.sequence,
        "missing_edges": last.sequence - first.sequence + 1 - count,
        "rejected_edges": count - accepted,
        "seconds": int(seconds[-1]),
        "ticks_per_second": None,
        "scale_error_ppm": None,
        "scale_standard_error_ppm": None,
        "residual_rms_ticks": None,
        "max_abs_residual_ticks": None,
    }
    if accepted < LINE_POINTS:
        return block
    mean_seconds = _total(seconds) / accepted
    mean_ticks = _total(ticks) / accepted
    spread = _total([(x - mean_seconds) * (x - mean_seconds) for x in seconds])
    covariance = _total(
        [(x - mean_seconds) * (y - mean_ticks) for x, y in zip(seconds, ticks, strict=True)]
    )
    slope = covariance / spread
    residuals = [
        (y - mean_ticks) - slope * (x - mean_seconds) for x, y in zip(seconds, ticks, strict=True)
    ]
    squares = _total([residual * residual for residual in residuals])
    variance = QUANTIZATION_VARIANCE
    if accepted > LINE_POINTS:
        variance = max(squares / (accepted - LINE_POINTS), QUANTIZATION_VARIANCE)
        block["residual_rms_ticks"] = math.sqrt(squares / accepted)
    block["ticks_per_second"] = slope
    block["scale_error_ppm"] = (slope - clock_hz) / clock_hz * PARTS_PER_MILLION
    block["scale_standard_error_ppm"] = math.sqrt(variance / spread) / clock_hz * PARTS_PER_MILLION
    block["max_abs_residual_ticks"] = max(abs(residual) for residual in residuals)
    return block
