# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — binary event stream decoder

"""Decode hash-bound, little-endian fabric event records without silent loss.

A profile's reference events, such as the CONTROL profile's pulse per second, share the record
format but not the cycle order: the fabric writes such a record into a slot that no cycle event
claims, so it can follow cycle records with later counter values. Its cycle field holds the
reference's own sequence number, and the decoder checks each reference kind on its own.
"""

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


@dataclass(frozen=True, slots=True)
class ReferenceEdge:
    """One edge of an external time reference, timestamped by the fabric witness.

    Attributes
    ----------
    name
        Reference event name from the measurement-domain contract.
    sequence
        The reference's own edge count when this edge arrived; a gap is an edge not recorded.
    ticks
        Free-running fabric counter value, in clock ticks.
    """

    name: str
    sequence: int
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
    """Decode and validate the complete binary event file, returning its cycle events.

    The reference records are checked as in :func:`decode_stream` and left out.

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
        events from another profile, non-monotonic time or cycle order,
        repeated event kinds within one cycle, or reference records out of order.
    """
    return decode_stream(content, contracts, profile_name, cycle_count)[0]


def decode_stream(
    content: bytes, contracts: dict[str, Any], profile_name: str, cycle_count: int
) -> tuple[tuple[Event, ...], tuple[ReferenceEdge, ...]]:
    """Decode and validate the complete binary event file, cycle and reference records apart.

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
    tuple[tuple[Event, ...], tuple[ReferenceEdge, ...]]
        Cycle events and reference edges, each in capture order.

    Raises
    ------
    ValueError
        If the file has malformed records, reserved bits, unknown codes,
        events from another profile, non-monotonic time or cycle order,
        repeated event kinds within one cycle, or a reference record whose
        sequence number or counter value does not exceed the previous one
        of its kind.
    """
    check_event_file(content)
    profile = contracts["event_profiles"][profile_name]
    names = set(profile["periodic_events"]) | set(profile["occasional_events"])
    allowed = {code: name for name, code in contracts["event_codes"].items() if name in names}
    references = {
        code: name
        for name, code in contracts["event_codes"].items()
        if name in profile.get("reference_events", [])
    }
    events: list[Event] = []
    edges: list[ReferenceEdge] = []
    latest: dict[str, ReferenceEdge] = {}
    seen: set[tuple[int, str]] = set()
    for index in range(len(content) // EVENT_RECORD.size):
        fields = EVENT_RECORD.unpack_from(content, index * EVENT_RECORD.size)
        if fields[0] in references:
            edge = _reference_edge(index, fields, references[fields[0]], latest)
            latest[edge.name] = edge
            edges.append(edge)
            continue
        event = record_event(index, fields, allowed, profile_name, cycle_count)
        if events and (event.ticks < events[-1].ticks or event.cycle < events[-1].cycle):
            message = f"event record {index}: order is not monotonic"
            raise ValueError(message)
        if (event.cycle, event.name) in seen:
            message = f"event record {index}: duplicate {event.name} in cycle {event.cycle}"
            raise ValueError(message)
        seen.add((event.cycle, event.name))
        events.append(event)
    return tuple(events), tuple(edges)


def _reference_edge(
    index: int,
    fields: tuple[int, int, int, int, int],
    name: str,
    latest: dict[str, ReferenceEdge],
) -> ReferenceEdge:
    """Return one reference record's edge after checking its reserved bits and its order.

    Parameters
    ----------
    index
        Zero-based record index, named in refusals.
    fields
        Code, reserved byte, reserved word, sequence number and ticks of the record.
    name
        Reference event name of the record's code.
    latest
        The previous edge of each reference kind.

    Returns
    -------
    ReferenceEdge
        The record's edge.

    Raises
    ------
    ValueError
        If a reserved bit is set, or the sequence number or counter value does not exceed that of
        the previous edge of the same kind.
    """
    _, reserved_byte, reserved_word, sequence, ticks = fields
    if reserved_byte or reserved_word:
        message = f"event record {index}: reserved bits must be zero"
        raise ValueError(message)
    previous = latest.get(name)
    if previous is not None and (sequence <= previous.sequence or ticks <= previous.ticks):
        message = f"event record {index}: {name} order is not monotonic"
        raise ValueError(message)
    return ReferenceEdge(name, sequence, ticks)
