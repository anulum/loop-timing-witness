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
import re
from collections import defaultdict
from decimal import Decimal
from itertools import pairwise
from math import sqrt
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .event_stream import Event

TRACKING_COLUMNS = ("cycle", "reference", "output")
POWER_COLUMNS = ("timebase_ticks", "rail", "voltage_v", "current_a", "energy_j")
MINIMUM_POWER_SAMPLES = 2
MEASUREMENT_DIGITS = 28
MEASUREMENT_EXPONENT = 99
_MEASUREMENT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_NON_FINITE = re.compile(r"[+-]?(?:inf(?:inity)?|s?nan[0-9]*)", re.IGNORECASE | re.ASCII)
_EXPONENT_DIGITS = 6
_COUNT_LIMIT = 2**64
_COUNT_DIGITS = len(str(_COUNT_LIMIT))


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
    try:
        header = tuple(reader.fieldnames or ())
        if header != columns:
            message = f"CSV header must be {','.join(columns)}"
            raise ValueError(message)
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


def count(value: str, field: str) -> int:
    """Parse one canonical nonnegative decimal integer below 2**64.

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
        If the value is not a nonnegative base-10 integer below 2**64.
    """
    if not value.isascii() or not value.isdecimal():
        message = f"{field} must be a nonnegative decimal integer"
        raise ValueError(message)
    digits = value.lstrip("0")
    if len(digits) > _COUNT_DIGITS or int(digits or "0") >= _COUNT_LIMIT:
        message = f"{field} must be below 2**64"
        raise ValueError(message)
    return int(digits or "0")


def _decimal_shift(exponent: str, whole: str, fraction: str, significant: int, field: str) -> int:
    """Return the decimal exponent of a measurement after checking its range.

    Parameters
    ----------
    exponent
        Exponent text after ``e``, possibly empty or signed.
    whole, fraction
        Integer digits without leading zeros, and fraction digits.
    significant
        Count of significant digits.
    field
        Name used in a refusal message.

    Returns
    -------
    int
        The exponent's value.

    Raises
    ------
    ValueError
        If the exponent text is too long, there are too many significant digits,
        or the magnitude lies outside 10**-99 to 10**100.
    """
    power = exponent.lstrip("+-").lstrip("0")
    if len(power) > _EXPONENT_DIGITS:
        message = f"{field} is outside the supported decimal range"
        raise ValueError(message)
    shift = -int(power or "0") if exponent.startswith("-") else int(power or "0")
    leading = len(whole) - 1 if whole else len(fraction.lstrip("0")) - len(fraction) - 1
    if significant > MEASUREMENT_DIGITS or abs(shift + leading) > MEASUREMENT_EXPONENT:
        message = f"{field} is outside the supported decimal range"
        raise ValueError(message)
    return shift


def measurement(value: str, field: str) -> Decimal:
    """Parse one finite decimal measurement within the supported range.

    The value is ASCII: an optional sign, digits with an optional decimal
    point, and an optional exponent. It has at most 28 significant digits,
    not counting leading or trailing zeros, and is zero or has a magnitude
    from 10**-99 up to, but not including, 10**100. Every sum, product and
    quotient of such values is then exact or correctly rounded in the
    default 28-digit decimal context and converts to a finite float.

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
        If the value is not a finite decimal in the supported range.
    """
    if _NON_FINITE.fullmatch(value):
        message = f"{field} must be finite"
        raise ValueError(message)
    if not _MEASUREMENT.fullmatch(value):
        message = f"{field} is not a decimal"
        raise ValueError(message)
    mantissa, _, exponent = value.lower().partition("e")
    negative = mantissa.startswith("-")
    whole, _, fraction = mantissa.lstrip("+-").partition(".")
    whole = whole.lstrip("0")
    digits = (whole + fraction).lstrip("0").rstrip("0")
    if not digits:
        return Decimal("-0" if negative else "0")
    shift = _decimal_shift(exponent, whole, fraction, len(digits), field)
    # Built from its digits, as Decimal(value) represents it, so that no implementation
    # of the decimal module converts a long run of leading zeros to an integer.
    coefficient = tuple(int(digit) for digit in (whole + fraction).lstrip("0"))
    return Decimal((int(negative), coefficient, shift - len(fraction)))


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
        cycle = count(row["cycle"], "cycle")
        if cycle >= cycle_count or cycle in observations:
            message = f"tracking cycle {cycle} is duplicated or outside the run"
            raise ValueError(message)
        reference = measurement(row["reference"], "reference")
        output = measurement(row["output"], "output")
        observations[cycle] = reference - output
    needed = set(range(int(warmup_cycles), int(cycle_count)))
    if not needed.issubset(observations):
        message = "tracking file lacks an analysed cycle"
        raise ValueError(message)
    errors = [observations[cycle] for cycle in sorted(needed)]
    return {
        "status": "available",
        "unit": unit,
        "sample_count": len(errors),
        **error_statistics(errors),
    }


def error_statistics(errors: list[Decimal]) -> dict[str, float]:
    """Return the RMS and peak absolute value of nonempty exact tracking errors.

    Parameters
    ----------
    errors
        Reference minus output for each analysed cycle, at least one.

    Returns
    -------
    dict[str, float]
        ``rms`` from the exact decimal mean square and ``peak_absolute``.
    """
    mean_square = sum((error * error for error in errors), Decimal(0)) / len(errors)
    return {
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
        ticks = count(row["timebase_ticks"], "timebase_ticks")
        rail = row["rail"]
        if rail not in rails or rail in samples[ticks]:
            message = f"power rail {rail!r} is unknown or duplicated at tick {ticks}"
            raise ValueError(message)
        for field in ("voltage_v", "current_a", "energy_j"):
            value = measurement(row[field], field)
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


def _cycle_ticks(events: tuple[Event, ...], profile_name: str, warmup_cycles: int) -> list[int]:
    """Return the sorted anchor ticks of the analysed cycles.

    Parameters
    ----------
    events
        Validated fabric events.
    profile_name
        ``CONTROL`` cycles are anchored on ``SAMPLE_READY``, others on ``INPUT_WRITE``.
    warmup_cycles
        Initial cycles excluded from results.

    Returns
    -------
    list[int]
        Fabric ticks of every analysed cycle's anchor event, in order.
    """
    anchor = "SAMPLE_READY" if profile_name == "CONTROL" else "INPUT_WRITE"
    return sorted(
        event.ticks for event in events if event.name == anchor and event.cycle >= warmup_cycles
    )


def _window_cycles(start: int, end: int, cycle_ticks: list[int], warmup_cycles: int) -> int:
    """Count the analysed cycles one sampler window holds.

    Parameters
    ----------
    start, end
        Window bounds in fabric ticks; the end is exclusive.
    cycle_ticks
        Sorted anchor ticks of the analysed cycles.
    warmup_cycles
        Initial cycles excluded from results.

    Returns
    -------
    int
        Number of analysed cycle anchors in the window.

    Raises
    ------
    ValueError
        If a window holding analysed cycles begins before the first of them
        while a warm-up was discarded.
    """
    cycle_samples = sum(start <= tick < end for tick in cycle_ticks)
    if cycle_samples and warmup_cycles and start < cycle_ticks[0]:
        message = "power window overlaps discarded warm-up cycles"
        raise ValueError(message)
    return cycle_samples


def _rail_deltas(
    first: dict[str, Decimal], last: dict[str, Decimal], rails: list[str]
) -> dict[str, Decimal]:
    """Return each rail's cumulative-energy increase over one window.

    Parameters
    ----------
    first, last
        Cumulative joules by rail at the window's start and end.
    rails
        Exact board rail names, in declaration order.

    Returns
    -------
    dict[str, Decimal]
        Joules added on each rail.

    Raises
    ------
    ValueError
        If cumulative energy decreases on a rail.
    """
    deltas = {}
    for rail in rails:
        delta = last[rail] - first[rail]
        if delta < 0:
            message = f"cumulative energy decreases for {rail}"
            raise ValueError(message)
        deltas[rail] = delta
    return deltas


def _window_energy(
    samples: dict[int, dict[str, Decimal]],
    rails: list[str],
    cycle_ticks: list[int],
    warmup_cycles: int,
) -> tuple[dict[str, Decimal], int, int]:
    """Sum each rail's energy over the sampler windows that hold analysed cycles.

    Parameters
    ----------
    samples
        Cumulative joules by fabric tick and rail.
    rails
        Exact board rail names from the measurement-domain contract.
    cycle_ticks
        Sorted anchor ticks of the analysed cycles.
    warmup_cycles
        Initial cycles excluded from results.

    Returns
    -------
    tuple[dict[str, Decimal], int, int]
        Joules per rail over the contributing windows, the cycles they hold and
        the number of contributing windows.

    Raises
    ------
    ValueError
        If a window overlaps the warm-up, cumulative energy decreases, or the
        windows do not hold every analysed cycle.
    """
    energy = {rail: Decimal(0) for rail in rails}
    covered_cycles = 0
    windows = 0
    for start, end in pairwise(sorted(samples)):
        cycle_samples = _window_cycles(start, end, cycle_ticks, warmup_cycles)
        deltas = _rail_deltas(samples[start], samples[end], rails)
        if cycle_samples:
            for rail in rails:
                energy[rail] += deltas[rail]
            covered_cycles += cycle_samples
            windows += 1
    if covered_cycles != len(cycle_ticks) or not covered_cycles:
        message = "power windows do not cover every analysed cycle"
        raise ValueError(message)
    return energy, covered_cycles, windows


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
    cycle_ticks = _cycle_ticks(events, profile_name, warmup_cycles)
    energy, covered, windows = _window_energy(samples, rails, cycle_ticks, warmup_cycles)
    per_rail = {rail: float(energy[rail] / covered) for rail in rails}
    return {
        "status": "available",
        "unit": "J/cycle",
        "sample_count": covered,
        "window_count": windows,
        "per_rail": per_rail,
        "total": sum(per_rail.values()),
    }
