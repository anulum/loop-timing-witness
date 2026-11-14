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


def check_event_file(content: bytes) -> None:
    """Refuse an event file that is empty or not a whole number of records.

    Parameters
    ----------
    content
        Exact bytes whose digest matched the run manifest.

    Raises
    ------
    ValueError
        If the file is not a whole number of 16-byte records, or is empty.
    """
    if len(content) % EVENT_RECORD.size:
        message = "event file is not a whole number of 16-byte records"
        raise ValueError(message)
    if not content:
        message = "event file is empty"
        raise ValueError(message)


def record_event(
    index: int,
    fields: tuple[int, int, int, int, int],
    allowed: dict[int, str],
    profile_name: str,
    cycle_count: int,
) -> Event:
    """Return one record's event after checking its reserved bits, code and cycle.

    Parameters
    ----------
    index
        Zero-based record index, named in refusals.
    fields
        Code, reserved byte, reserved word, cycle and ticks of the record.
    allowed
        Event name by code, for the codes of the run's profile.
    profile_name
        ``CONTROL`` or ``COMPUTE``.
    cycle_count
        Number of declared cycles in the run.

    Returns
    -------
    Event
        The record's event.

    Raises
    ------
    ValueError
        If a reserved bit is set, the code is not in the profile or the cycle is outside the run.
    """
    event_code, reserved_byte, reserved_word, cycle, ticks = fields
    if reserved_byte or reserved_word:
        message = f"event record {index}: reserved bits must be zero"
        raise ValueError(message)
    name = allowed.get(event_code)
    if name is None:
        message = f"event record {index}: code {event_code} is not in {profile_name}"
        raise ValueError(message)
    if cycle >= cycle_count:
        message = f"event record {index}: cycle is outside the run"
        raise ValueError(message)
    return Event(name, cycle, ticks)


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
    check_event_file(content)
    profile = contracts["event_profiles"][profile_name]
    names = set(profile["periodic_events"]) | set(profile["occasional_events"])
    allowed = {code: name for name, code in contracts["event_codes"].items() if name in names}
    events: list[Event] = []
    seen: set[tuple[int, str]] = set()
    for index in range(len(content) // EVENT_RECORD.size):
        fields = EVENT_RECORD.unpack_from(content, index * EVENT_RECORD.size)
        event = record_event(index, fields, allowed, profile_name, cycle_count)
        if events and (event.ticks < events[-1].ticks or event.cycle < events[-1].cycle):
            message = f"event record {index}: order is not monotonic"
            raise ValueError(message)
        if (event.cycle, event.name) in seen:
            message = f"event record {index}: duplicate {event.name} in cycle {event.cycle}"
            raise ValueError(message)
        seen.add((event.cycle, event.name))
        events.append(event)
    return tuple(events)
