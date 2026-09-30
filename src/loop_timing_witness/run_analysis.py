# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — event statistics

"""Derive cycle intervals, deadline misses and fault timing from fabric events."""

from __future__ import annotations

from collections import defaultdict
from math import ceil, floor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_stream import Event


def distribution(values: list[int]) -> dict[str, int | float | None]:
    """Return a documented Type-7 empirical distribution in clock ticks.

    Parameters
    ----------
    values
        Nonnegative clock-tick intervals. An empty sample is explicit.

    Returns
    -------
    dict[str, int | float | None]
        Sample count, median, p95, p99, p99.9 and maximum. Quantiles use
        linear interpolation at ``(n - 1) * p`` on zero-based sorted data.

    Raises
    ------
    ValueError
        If an interval is negative.
    """
    if any(value < 0 for value in values):
        message = "negative event interval"
        raise ValueError(message)
    count = len(values)
    if not count:
        return {
            "sample_count": 0,
            "median_ticks": None,
            "p95_ticks": None,
            "p99_ticks": None,
            "p999_ticks": None,
            "maximum_ticks": None,
        }
    ordered = sorted(values)

    def quantile(p: float) -> float:
        position = (count - 1) * p
        low = floor(position)
        high = ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    return {
        "sample_count": count,
        "median_ticks": quantile(0.5),
        "p95_ticks": quantile(0.95),
        "p99_ticks": quantile(0.99),
        "p999_ticks": quantile(0.999),
        "maximum_ticks": ordered[-1],
    }


def _cycle_events(events: tuple[Event, ...]) -> dict[int, dict[str, int]]:
    """Index validated events by cycle and event name.

    Parameters
    ----------
    events
        Events with unique ``(cycle, name)`` pairs.

    Returns
    -------
    dict[int, dict[str, int]]
        Fabric ticks for each event in each cycle.
    """
    cycles: dict[int, dict[str, int]] = defaultdict(dict)
    for event in events:
        cycles[event.cycle][event.name] = event.ticks
    return dict(cycles)


def _intervals(
    cycles: dict[int, dict[str, int]], profile: dict[str, Any], warmup_cycles: int
) -> tuple[dict[str, list[int]], list[dict[str, int | str]]]:
    """Calculate same-cycle contract intervals and per-cycle CSV rows.

    Parameters
    ----------
    cycles
        Decoded event ticks by cycle.
    profile
        One validated event profile.
    warmup_cycles
        Cycles excluded from analysis.

    Returns
    -------
    tuple[dict[str, list[int]], list[dict[str, int | str]]]
        Distribution inputs and individual interval rows.

    Raises
    ------
    ValueError
        If an end event precedes its start in the same cycle.
    """
    values: dict[str, list[int]] = {
        interval["name"]: []
        for interval in profile["intervals"]
        if interval["name"] != "time_to_safe_state"
    }
    rows: list[dict[str, int | str]] = []
    for cycle, observed in sorted(cycles.items()):
        if cycle < warmup_cycles:
            continue
        for interval in profile["intervals"]:
            name = interval["name"]
            if name == "time_to_safe_state":
                continue
            start = observed.get(interval["start_event"])
            end = observed.get(interval["end_event"])
            if start is None or end is None:
                continue
            ticks = end - start
            if ticks < 0:
                message = f"cycle {cycle}: {name} ends before it starts"
                raise ValueError(message)
            values[name].append(ticks)
            rows.append({"cycle": cycle, "interval": name, "ticks": ticks})
    return values, rows


def _accept_injection(open_injection: int | None, injection: int, cycle: int) -> int:
    """Refuse a second injected fault before the first is detected.

    Parameters
    ----------
    open_injection
        Pending injection tick, if any.
    injection
        New injection tick.
    cycle
        Cycle number for refusal text.

    Returns
    -------
    int
        New pending injection tick.

    Raises
    ------
    ValueError
        If an earlier injected fault is still pending.
    """
    if open_injection is not None:
        message = f"cycle {cycle}: fault injection overlaps an undetected fault"
        raise ValueError(message)
    return injection


def _control_faults(
    cycles: dict[int, dict[str, int]], warmup_cycles: int, cycle_count: int
) -> tuple[dict[str, Any], list[int], list[int]]:
    """Count deadlines and pair fault, detection and safe-state events.

    Parameters
    ----------
    cycles
        Event ticks by cycle.
    warmup_cycles
        Excluded prefix.
    cycle_count
        Declared control cycles.

    Returns
    -------
    tuple[dict[str, Any], list[int], list[int]]
        Deadline/fault counts and detected/safe interval samples.

    Raises
    ------
    ValueError
        If detection or safe state precedes its causal event.
    """
    misses = 0
    observed_deadlines = 0
    injections = 0
    detected: list[int] = []
    safe: list[int] = []
    open_injection: int | None = None
    first_missed_deadline: int | None = None
    for cycle in range(warmup_cycles, cycle_count):
        observed = cycles.get(cycle, {})
        injection = observed.get("FAULT_INJECTED")
        if injection is not None:
            injections += 1
            open_injection = _accept_injection(open_injection, injection, cycle)
        detection = observed.get("FAULT_DETECTED")
        if detection is not None:
            if open_injection is None or detection < open_injection:
                message = f"cycle {cycle}: fault detection lacks a prior injection"
                raise ValueError(message)
            detected.append(detection - open_injection)
            open_injection = None
        deadline = observed.get("DEADLINE")
        if deadline is not None:
            observed_deadlines += 1
            write = observed.get("ACT_WRITE")
            if write is None or write >= deadline:
                misses += 1
                if first_missed_deadline is None:
                    first_missed_deadline = deadline
            else:
                first_missed_deadline = None
        safe_state = observed.get("SAFE_STATE")
        if safe_state is not None:
            if first_missed_deadline is None or safe_state < first_missed_deadline:
                message = f"cycle {cycle}: safe state lacks a prior missed deadline"
                raise ValueError(message)
            safe.append(safe_state - first_missed_deadline)
            first_missed_deadline = None
    return (
        {
            "observed_deadlines": observed_deadlines,
            "deadline_misses": misses,
            "deadline_miss_rate": misses / observed_deadlines if observed_deadlines else None,
            "fault_injections": injections,
            "fault_detections": len(detected),
            "undetected_faults": injections - len(detected),
            "safe_state_events": len(safe),
        },
        detected,
        safe,
    )


def analyse_events(
    events: tuple[Event, ...], profile: dict[str, Any], cycle_count: int, warmup_cycles: int
) -> tuple[dict[str, Any], list[dict[str, int | str]]]:
    """Analyse all post-warm-up events under one profile.

    Parameters
    ----------
    events
        Validated fabric events.
    profile
        Validated event profile.
    cycle_count
        Declared run length.
    warmup_cycles
        Initial cycles omitted from statistics.

    Returns
    -------
    tuple[dict[str, Any], list[dict[str, int | str]]]
        Report summary and per-cycle interval rows.
    """
    cycles = _cycle_events(events)
    values, rows = _intervals(cycles, profile, warmup_cycles)
    if "DEADLINE" in profile["periodic_events"]:
        control, detected, safe = _control_faults(cycles, warmup_cycles, cycle_count)
        values["fault_detection"] = detected
        values["time_to_safe_state"] = safe
    else:
        control = None
    analysed = [event for event in events if event.cycle >= warmup_cycles]
    duration = analysed[-1].ticks - analysed[0].ticks if analysed else 0
    return (
        {
            "event_count": len(analysed),
            "cycle_count": cycle_count - warmup_cycles,
            "duration_ticks": duration,
            "intervals": {name: distribution(samples) for name, samples in values.items()},
            "control": control,
        },
        rows,
    )
