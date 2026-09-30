# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tracking and energy series

"""Validate independent run series and derive control and energy metrics."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from math import sqrt
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .event_stream import Event

TRACKING_COLUMNS = ("cycle", "reference", "output")
POWER_COLUMNS = ("timebase_ticks", "rail", "voltage_v", "current_a", "energy_j")
MINIMUM_POWER_SAMPLES = 2


def _rows(content: bytes, columns: tuple[str, ...]) -> list[dict[str, str]]:
    """Read a strict UTF-8 CSV table with one exact header.

    Parameters
    ----------
    content
        Hash-bound CSV bytes.
    columns
        Required header fields, in order.

    Returns
    -------
    list[dict[str, str]]
        Nonempty data rows without missing or excess cells.

    Raises
    ------
    ValueError
        If decoding or CSV structure fails.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = "series file is not UTF-8"
        raise ValueError(message) from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != columns:
        message = f"CSV header must be {','.join(columns)}"
        raise ValueError(message)
    try:
        rows = list(reader)
    except csv.Error as exc:
        message = f"invalid CSV: {exc}"
        raise ValueError(message) from exc
    if not rows or any(
        None in row or any(value is None or value == "" for value in row.values()) for row in rows
    ):
        message = "CSV has no data or contains an incomplete row"
        raise ValueError(message)
    return cast("list[dict[str, str]]", rows)


def _integer(value: str, field: str) -> int:
    """Parse one canonical nonnegative decimal integer.

    Parameters
    ----------
    value
        CSV cell.
    field
        Name used in a refusal message.

    Returns
    -------
    int
        Parsed value.

    Raises
    ------
    ValueError
        If the value is not a nonnegative base-10 integer.
    """
    if not value.isascii() or not value.isdecimal():
        message = f"{field} must be a nonnegative decimal integer"
        raise ValueError(message)
    return int(value)


def _decimal(value: str, field: str) -> Decimal:
    """Parse one finite decimal measurement.

    Parameters
    ----------
    value
        CSV cell.
    field
        Name used in a refusal message.

    Returns
    -------
    Decimal
        Exact decimal representation.

    Raises
    ------
    ValueError
        If the value is not a finite decimal.
    """
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        message = f"{field} is not a decimal"
        raise ValueError(message) from exc
    if not result.is_finite():
        message = f"{field} must be finite"
        raise ValueError(message)
    return result


def tracking_error(
    content: bytes | None, cycle_count: int, warmup_cycles: int, unit: str
) -> dict[str, Any]:
    """Compute RMS and peak tracking error from one row per control cycle.

    Parameters
    ----------
    content
        Hash-bound tracking CSV, or ``None`` when no tracking series exists.
    cycle_count
        Declared total cycle count.
    warmup_cycles
        Initial cycles excluded from results.
    unit
        Plant output unit declared in the run manifest.

    Returns
    -------
    dict[str, Any]
        Metric status, unit, sample count, RMS and peak absolute error.

    Raises
    ------
    ValueError
        If any cycle is duplicated, missing or outside the run.
    """
    if content is None:
        return {"status": "unavailable", "reason": "tracking file not supplied", "unit": unit}
    observations: dict[int, Decimal] = {}
    for row in _rows(content, TRACKING_COLUMNS):
        cycle = _integer(row["cycle"], "cycle")
        if cycle >= cycle_count or cycle in observations:
            message = f"tracking cycle {cycle} is duplicated or outside the run"
            raise ValueError(message)
        reference = _decimal(row["reference"], "reference")
        output = _decimal(row["output"], "output")
        observations[cycle] = reference - output
    needed = set(range(warmup_cycles, cycle_count))
    if not needed.issubset(observations):
        message = "tracking file lacks an analysed cycle"
        raise ValueError(message)
    errors = [observations[cycle] for cycle in sorted(needed)]
    mean_square = sum((error * error for error in errors), Decimal(0)) / len(errors)
    return {
        "status": "available",
        "unit": unit,
        "sample_count": len(errors),
        "rms": sqrt(float(mean_square)),
        "peak_absolute": float(max(abs(error) for error in errors)),
    }


def _power_samples(content: bytes, rails: list[str]) -> dict[int, dict[str, Decimal]]:
    """Parse complete cumulative-energy samples for every declared rail.

    Parameters
    ----------
    content
        Hash-bound power CSV.
    rails
        Exact board rail names from the measurement-domain contract.

    Returns
    -------
    dict[int, dict[str, Decimal]]
        Cumulative joules by fabric tick and rail.

    Raises
    ------
    ValueError
        If the table is incomplete or a value is invalid.
    """
    samples: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for row in _rows(content, POWER_COLUMNS):
        ticks = _integer(row["timebase_ticks"], "timebase_ticks")
        rail = row["rail"]
        if rail not in rails or rail in samples[ticks]:
            message = f"power rail {rail!r} is unknown or duplicated at tick {ticks}"
            raise ValueError(message)
        for field in ("voltage_v", "current_a", "energy_j"):
            value = _decimal(row[field], field)
            if value < 0:
                message = f"{field} cannot be negative"
                raise ValueError(message)
            if field == "energy_j":
                samples[ticks][rail] = value
    boundaries = sorted(samples)
    if len(boundaries) < MINIMUM_POWER_SAMPLES or any(
        set(samples[ticks]) != set(rails) for ticks in boundaries
    ):
        message = "power file needs at least two complete four-rail samples"
        raise ValueError(message)
    return dict(samples)


def energy_per_cycle(
    content: bytes | None,
    events: tuple[Event, ...],
    profile_name: str,
    warmup_cycles: int,
    rails: list[str],
) -> dict[str, Any]:
    """Integrate cumulative rail energy over counter-aligned cycle windows.

    Parameters
    ----------
    content
        Hash-bound power CSV, or ``None`` when no power series exists.
    events
        Validated fabric events.
    profile_name
        Determines the cycle anchor event.
    warmup_cycles
        Initial cycles excluded from results.
    rails
        Exact board rail names from the measurement-domain contract.

    Returns
    -------
    dict[str, Any]
        Mean joules per cycle for each rail and all rails combined, with
        contributing window and cycle counts. No per-cycle instantaneous
        measurement is inferred from the slower power sampler.

    Raises
    ------
    ValueError
        If cumulative energy decreases or no window contains a cycle.
    """
    if content is None:
        return {"status": "unavailable", "reason": "power file not supplied"}
    samples = _power_samples(content, rails)
    boundaries = sorted(samples)
    anchor = "SAMPLE_READY" if profile_name == "CONTROL" else "INPUT_WRITE"
    cycle_ticks = sorted(
        event.ticks for event in events if event.name == anchor and event.cycle >= warmup_cycles
    )
    energy = {rail: Decimal(0) for rail in rails}
    covered_cycles = 0
    windows = 0
    for start, end in pairwise(boundaries):
        cycle_samples = sum(start <= tick < end for tick in cycle_ticks)
        if cycle_samples and warmup_cycles and start < cycle_ticks[0]:
            message = "power window overlaps discarded warm-up cycles"
            raise ValueError(message)
        for rail in rails:
            delta = samples[end][rail] - samples[start][rail]
            if delta < 0:
                message = f"cumulative energy decreases for {rail}"
                raise ValueError(message)
            if cycle_samples:
                energy[rail] += delta
        if cycle_samples:
            covered_cycles += cycle_samples
            windows += 1
    if covered_cycles != len(cycle_ticks) or not covered_cycles:
        message = "power windows do not cover every analysed cycle"
        raise ValueError(message)
    per_rail = {rail: float(energy[rail] / covered_cycles) for rail in rails}
    return {
        "status": "available",
        "unit": "J/cycle",
        "sample_count": covered_cycles,
        "window_count": windows,
        "per_rail": per_rail,
        "total": sum(per_rail.values()),
    }
