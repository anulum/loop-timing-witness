# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capture-bound observed tracking coverage

"""Describe observed tracking without filling missed or unobserved control cycles."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, DecimalException
from math import isfinite, sqrt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from event_stream import Event


def _observations(content: bytes, cycle_count: int) -> dict[int, Decimal]:
    """Read finite, unique tracking observations within the declared run.

    Parameters
    ----------
    content
        Hash-bound CSV bytes; a header-only table represents zero observations.
    cycle_count
        Exclusive cycle bound.

    Returns
    -------
    dict of int to Decimal
        Signed reference-minus-output errors by observed cycle.
    """
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""), strict=True)
    if reader.fieldnames != ["cycle", "reference", "output"]:
        message = "observed tracking CSV header must be cycle,reference,output"
        raise ValueError(message)
    result: dict[int, Decimal] = {}
    try:
        for row in reader:
            if None in row or any(value is None or value == "" for value in row.values()):
                message = "observed tracking contains an incomplete row"
                raise ValueError(message)
            raw_cycle = row["cycle"]
            if not raw_cycle.isascii() or not raw_cycle.isdecimal():
                message = "observed tracking cycle must be a nonnegative decimal integer"
                raise ValueError(message)
            cycle = int(raw_cycle)
            if cycle >= cycle_count or cycle in result:
                message = "observed tracking cycle is duplicated or outside the run"
                raise ValueError(message)
            reference, output = Decimal(row["reference"]), Decimal(row["output"])
            if not reference.is_finite() or not output.is_finite():
                message = "observed tracking values must be finite"
                raise ValueError(message)
            result[cycle] = reference - output
    except (csv.Error, DecimalException) as exc:
        message = f"invalid observed tracking CSV: {exc}"
        raise ValueError(message) from exc
    return result


def observed_tracking_error(
    content: bytes, events: tuple[Event, ...], cycle_count: int, warmup_cycles: int, unit: str
) -> dict[str, Any]:
    """Compute an explicitly scoped metric for every captured sample-read observation.

    Parameters
    ----------
    content
        Hash-bound tracking CSV.
    events
        Decoded hash-bound fabric records, including actual SAMPLE_READ events.
    cycle_count
        Declared run length.
    warmup_cycles
        Excluded initial cycles.
    unit
        Declared plant output unit.

    Returns
    -------
    dict of str to Any
        Observed-only errors with sample count, missing cycles and coverage fraction.
        Partial coverage never represents a complete run metric.

    Raises
    ------
    ValueError
        If observations differ from captured reads or CSV values are invalid.
    """
    observations = _observations(content, cycle_count)
    captured = {event.cycle for event in events if event.name == "SAMPLE_READ"}
    if set(observations) != captured:
        message = "observed tracking cycles do not match captured SAMPLE_READ events"
        raise ValueError(message)
    needed = set(range(warmup_cycles, cycle_count))
    selected = sorted(needed & observations.keys())
    missing = sorted(needed - observations.keys())
    result: dict[str, Any] = {
        "status": "partial" if missing else "available",
        "sampling": "observed",
        "unit": unit,
        "sample_count": len(selected),
        "expected_cycle_count": len(needed),
        "missing_cycles": missing,
        "coverage_fraction": len(selected) / len(needed),
    }
    if not selected:
        result.update(status="unavailable", reason="no observed post-warmup samples")
        return result
    errors = [observations[cycle] for cycle in selected]
    try:
        mean_square = sum((error * error for error in errors), Decimal(0)) / len(errors)
        rms = sqrt(float(mean_square))
        peak = float(max(abs(error) for error in errors))
    except (DecimalException, OverflowError) as exc:
        message = "observed tracking metrics exceed the numeric range"
        raise ValueError(message) from exc
    if not isfinite(rms) or not isfinite(peak):
        message = "observed tracking metrics exceed the numeric range"
        raise ValueError(message)
    result.update(rms=rms, peak_absolute=peak)
    return result
