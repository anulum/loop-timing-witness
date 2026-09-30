# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP logger completion and captured stream agreement

"""Require one logger receipt after drain and compare its counts with decoded raw outputs."""

from __future__ import annotations

from dataclasses import dataclass

from .event_stream import decode_events
from .manifest_io import parse_json_object
from .native_tracking import decode_tracking

PREFIX = b"WITNESS_AMP_COMPLETION "
FIELDS = frozenset({"samples", "events", "misses", "overflow", "safe", "thermal"})


@dataclass(frozen=True)
class AmpCompletion:
    """Actual final drain counters, distinct from target exit status or physical qualification.

    Parameters
    ----------
    samples
        Observed telemetry rows.
    events
        Observed drained records.
    misses
        Actual fabric deadline-miss counter.
    overflow
        Actual fabric dropped-record counter.
    safe
        Actual latched fabric safe state.
    thermal
        Actual read-only plant selector observed from the running RTL.
    """

    samples: int
    events: int
    misses: int
    overflow: int
    safe: bool
    thermal: bool


def completion_receipt(log: bytes) -> AmpCompletion:
    """Reject absent, repeated or malformed completion instead of trusting target exit alone.

    Parameters
    ----------
    log
        Complete actual simulator standard output and error bytes.

    Returns
    -------
    AmpCompletion
        Validated observed logger counters after stream closure.

    Raises
    ------
    ValueError
        If exactly one bounded, typed final receipt is not present.
    """
    records = [line[len(PREFIX) :] for line in log.splitlines() if line.startswith(PREFIX)]
    if len(records) != 1:
        message = "AMP requires exactly one actual logger completion receipt"
        raise ValueError(message)
    return decode_completion(records[0])


def decode_completion(content: bytes) -> AmpCompletion:
    """Admit complete JSON counter bytes from a native log or a hash-bound capture receipt.

    Parameters
    ----------
    content
        Complete original completion JSON, independent of native log line framing.

    Returns
    -------
    AmpCompletion
        Bounded native final counters and observed RTL plant selector.

    Raises
    ------
    ValueError
        If the complete object violates the native scalar and field contract.
    """
    data = parse_json_object(content, "AMP completion")
    if set(data) != FIELDS or any(type(data[name]) is not bool for name in ("safe", "thermal")):
        message = "AMP completion fields or safe-state type are invalid"
        raise ValueError(message)
    for name in FIELDS - {"safe", "thermal"}:
        limit = (1 << (32 if name in {"misses", "overflow"} else 64)) - 1
        if type(data[name]) is not int or not 0 <= data[name] <= limit:
            message = "AMP completion counters are outside the native ABI"
            raise ValueError(message)
    return AmpCompletion(
        data["samples"],
        data["events"],
        data["misses"],
        data["overflow"],
        data["safe"],
        data["thermal"],
    )


def validate_capture(
    completion: AmpCompletion, events: bytes, tracking: bytes, domain: bytes, cycles: int
) -> None:
    """Compare actual sample reads and final drain counters without filling missing cycles.

    Parameters
    ----------
    completion
        Actual native logger receipt after final drain.
    events
        Complete original binary event stream.
    tracking
        Complete original raw telemetry stream.
    domain
        Retained measurement-domain bytes declaring the event wire contract.
    cycles
        Admitted original configured cycle count.

    Raises
    ------
    ValueError
        If a stream is malformed, its observations disagree, or the FIFO overflowed.
    """
    contracts = parse_json_object(domain, "AMP measurement domain")["design_contracts"]
    decoded = decode_events(events, contracts, "CONTROL", cycles)
    observations = decode_tracking(tracking, cycles, completion.samples)
    observed_cycles = [row[0] for row in observations]
    read_cycles = [event.cycle for event in decoded if event.name == "SAMPLE_READ"]
    if completion.overflow:
        message = "AMP fabric FIFO overflow invalidates capture"
        raise ValueError(message)
    if len(decoded) != completion.events or read_cycles != observed_cycles:
        message = "AMP completion and event/telemetry observations disagree"
        raise ValueError(message)
