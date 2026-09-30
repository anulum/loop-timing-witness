# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — binary event stream decoder

"""Decode hash-bound, little-endian fabric event records without silent loss."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Final

EVENT_RECORD: Final = struct.Struct("<BBHIQ")


@dataclass(frozen=True, slots=True)
class Event:
    """One timestamp captured by the fabric witness.

    Attributes
    ----------
    name
        Event name from the measurement-domain contract.
    cycle
        Zero-based control or compute cycle identifier.
    ticks
        Free-running fabric counter value, in clock ticks.
    """

    name: str
    cycle: int
    ticks: int


def decode_events(
    content: bytes, contracts: dict[str, Any], profile_name: str, cycle_count: int
) -> tuple[Event, ...]:
    """Decode and validate the complete binary event file.

    Parameters
    ----------
    content
        Exact bytes whose digest matched the run manifest.
    contracts
        Validated measurement-domain design contracts.
    profile_name
        ``CONTROL`` or ``COMPUTE``.
    cycle_count
        Number of declared cycles in the run.

    Returns
    -------
    tuple[Event, ...]
        Events in capture order.

    Raises
    ------
    ValueError
        If the file has malformed records, reserved bits, unknown codes,
        events from another profile, non-monotonic time or cycle order, or
        repeated event kinds within one cycle.
    """
    if len(content) % EVENT_RECORD.size:
        message = "event file is not a whole number of 16-byte records"
        raise ValueError(message)
    if not content:
        message = "event file is empty"
        raise ValueError(message)
    profile = contracts["event_profiles"][profile_name]
    allowed = set(profile["periodic_events"]) | set(profile["occasional_events"])
    codes = {code: name for name, code in contracts["event_codes"].items()}
    events: list[Event] = []
    seen: set[tuple[int, str]] = set()
    previous_ticks = -1
    previous_cycle = -1
    for offset in range(0, len(content), EVENT_RECORD.size):
        event_code, reserved_byte, reserved_word, cycle, ticks = EVENT_RECORD.unpack_from(
            content, offset
        )
        if reserved_byte or reserved_word:
            message = f"event record {offset // EVENT_RECORD.size}: reserved bits must be zero"
            raise ValueError(message)
        name = codes.get(event_code)
        if name is None or name not in allowed:
            message = (
                f"event record {offset // EVENT_RECORD.size}: "
                f"code {event_code} is not in {profile_name}"
            )
            raise ValueError(message)
        if cycle >= cycle_count:
            message = f"event record {offset // EVENT_RECORD.size}: cycle is outside the run"
            raise ValueError(message)
        if ticks < previous_ticks or cycle < previous_cycle:
            message = f"event record {offset // EVENT_RECORD.size}: order is not monotonic"
            raise ValueError(message)
        key = (cycle, name)
        if key in seen:
            message = (
                f"event record {offset // EVENT_RECORD.size}: duplicate {name} in cycle {cycle}"
            )
            raise ValueError(message)
        seen.add(key)
        events.append(Event(name, cycle, ticks))
        previous_ticks = ticks
        previous_cycle = cycle
    return tuple(events)
