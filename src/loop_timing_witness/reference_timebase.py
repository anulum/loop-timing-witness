# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fabric timebase against a pulse-per-second reference

"""Fit the fabric counter against the edges of a pulse-per-second reference.

Each recorded edge pairs the reference's sequence number, one per second, with the counter value
the fabric captured. An ordinary least-squares line through these pairs gives the counter's ticks
per second; its scale error against the declared clock frequency is in parts per million, with the
standard error of the slope from the fit residuals. The result describes the counter relative to the
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
"""Edges that determine a line; a standard error needs one more."""


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
        numbers and the number of edges the sequence skips; with two or more edges the fitted ticks
        per second, the scale error in parts per million and the largest absolute residual; with
        three or more the standard error of the scale error and the root-mean-square residual, which
        are ``None`` below that, as are the fit values with one edge.
    """
    pulses = [edge for edge in edges if edge.name == REFERENCE_EVENT]
    if not pulses:
        return None
    count = len(pulses)
    first, last = pulses[0], pulses[-1]
    block: dict[str, Any] = {
        "event": REFERENCE_EVENT,
        "edges": count,
        "first_sequence": first.sequence,
        "last_sequence": last.sequence,
        "missing_edges": last.sequence - first.sequence + 1 - count,
        "ticks_per_second": None,
        "scale_error_ppm": None,
        "scale_standard_error_ppm": None,
        "residual_rms_ticks": None,
        "max_abs_residual_ticks": None,
    }
    if count < LINE_POINTS:
        return block
    seconds = [float(edge.sequence - first.sequence) for edge in pulses]
    ticks = [float(edge.ticks - first.ticks) for edge in pulses]
    mean_seconds = _total(seconds) / count
    mean_ticks = _total(ticks) / count
    spread = _total([(x - mean_seconds) * (x - mean_seconds) for x in seconds])
    covariance = _total(
        [(x - mean_seconds) * (y - mean_ticks) for x, y in zip(seconds, ticks, strict=True)]
    )
    slope = covariance / spread
    residuals = [
        (y - mean_ticks) - slope * (x - mean_seconds) for x, y in zip(seconds, ticks, strict=True)
    ]
    squares = _total([residual * residual for residual in residuals])
    block["ticks_per_second"] = slope
    block["scale_error_ppm"] = (slope - clock_hz) / clock_hz * PARTS_PER_MILLION
    block["max_abs_residual_ticks"] = max(abs(residual) for residual in residuals)
    if count > LINE_POINTS:
        block["scale_standard_error_ppm"] = (
            math.sqrt(squares / (count - LINE_POINTS) / spread) / clock_hz * PARTS_PER_MILLION
        )
        block["residual_rms_ticks"] = math.sqrt(squares / count)
    return block
