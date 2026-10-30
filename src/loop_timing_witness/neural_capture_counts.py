# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — neural capture counter and original-export reconciliation

"""Reconcile captured records with actual channel counts, preserving saturation bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .manifest_io import JsonInputRefusalError, parse_json_object
from .neural_event_stream import NEURAL_RECORD, NeuralCaptureRefusalError, NeuralChannel

COUNTS_SCHEMA_ID: Final = "loop-timing-witness.neural-capture-counts.v1"
MAX_RUN_COUNT: Final = (1 << 64) - 1
CHANNEL_COUNT: Final = 3
CHANNEL_FIELDS: Final = frozenset(
    {"role", "attempts", "accepted", "dropped", "drained", "overflowed"}
)


@dataclass(frozen=True, slots=True)
class NeuralCaptureCounts:
    """One channel's original capture-domain and drain counters.

    Attributes
    ----------
    role
        Declared input, state or service channel.
    attempts, accepted
        Unsigned 64-bit run counts, admitted before their wrap.
    dropped
        Actual saturating overflow counter, not reconstructed after saturation.
    drained
        Original count of valid records delivered by the drain interface.
    overflowed
        Original sticky capture-domain overflow flag.
    drop_counter_bits
        Compiled overflow-counter width, between one and 32 inclusive.
    """

    role: str
    attempts: int
    accepted: int
    dropped: int
    drained: int
    overflowed: bool
    drop_counter_bits: int


@dataclass(frozen=True, slots=True)
class NeuralCaptureAccounting:
    """Observed export size, drop-count interpretation and completeness failures.

    Attributes
    ----------
    observed_records
        Actual decoded data plus marker records in the original channel export.
    dropped_lower_bound
        The original counter value, including when it reached its maximum.
    drop_count_exact
        False at the counter maximum, where additional drops cannot be excluded.
    refusals
        Located loss, accounting or incomplete-export failures. No refusal here
        proves only these count predicates, not source, phase or tail acceptance.
    """

    observed_records: int
    dropped_lower_bound: int
    drop_count_exact: bool
    refusals: tuple[str, ...]


def _unsigned(value: object, maximum: int, field: str) -> int:
    """Read a bounded unsigned count without treating a boolean as an integer.

    Parameters
    ----------
    value
        Original declared field value.
    maximum
        Inclusive maximum representable value.
    field
        Located declaration name for refusal text.

    Returns
    -------
    int
        Exact validated value.

    Raises
    ------
    NeuralCaptureRefusalError
        If the value has the wrong type or is outside the finite range.
    """
    if type(value) is not int or not 0 <= value <= maximum:
        message = f"Invalid neural capture counter: {field}."
        raise NeuralCaptureRefusalError(message)
    return value


def _decode_channel(value: object, role: str, bits: int) -> NeuralCaptureCounts:
    """Decode one closed channel object in its declared semantic position.

    Parameters
    ----------
    value
        Original JSON channel object.
    role
        Required role at this channel position.
    bits
        Validated compiled overflow-counter width.

    Returns
    -------
    NeuralCaptureCounts
        Typed original fields, without repaired or inferred counts.

    Raises
    ------
    NeuralCaptureRefusalError
        If the object, role, fields or counter declarations are invalid.
    """
    if not isinstance(value, dict) or set(value) != CHANNEL_FIELDS or value["role"] != role:
        message = f"Invalid neural capture counter channel: {role}."
        raise NeuralCaptureRefusalError(message)
    overflowed = value["overflowed"]
    if type(overflowed) is not bool:
        message = f"Invalid neural capture overflow flag: {role}."
        raise NeuralCaptureRefusalError(message)
    return NeuralCaptureCounts(
        role,
        _unsigned(value["attempts"], MAX_RUN_COUNT, f"{role}.attempts"),
        _unsigned(value["accepted"], MAX_RUN_COUNT, f"{role}.accepted"),
        _unsigned(value["dropped"], (1 << bits) - 1, f"{role}.dropped"),
        _unsigned(value["drained"], MAX_RUN_COUNT, f"{role}.drained"),
        overflowed,
        bits,
    )


def decode_neural_capture_counts(
    content: bytes,
) -> tuple[NeuralCaptureCounts, NeuralCaptureCounts, NeuralCaptureCounts]:
    """Decode a complete versioned counter receipt for three original channels.

    Parameters
    ----------
    content
        Exact UTF-8 receipt bytes whose file reference has already been verified.
        The closed root contains schema_id, drop_counter_bits and channels in
        input/state/service order. Each channel supplies only role, attempts,
        accepted, dropped, drained and overflowed.

    Returns
    -------
    tuple[NeuralCaptureCounts, NeuralCaptureCounts, NeuralCaptureCounts]
        Three original channel snapshots with finite, typed declarations.

    Raises
    ------
    NeuralCaptureRefusalError
        If JSON syntax, duplicate keys, schema, fields, role order or types fail.
    """
    if type(content) is not bytes:
        message = "Neural capture counter receipt must be bytes."
        raise NeuralCaptureRefusalError(message)
    try:
        root = parse_json_object(content, "neural capture counts")
    except JsonInputRefusalError as exc:
        raise NeuralCaptureRefusalError(str(exc)) from exc
    if set(root) != {"schema_id", "drop_counter_bits", "channels"} or (
        root["schema_id"] != COUNTS_SCHEMA_ID
    ):
        message = "Invalid neural capture counter receipt schema."
        raise NeuralCaptureRefusalError(message)
    bits = _unsigned(root["drop_counter_bits"], 32, "drop_counter_bits")
    if bits == 0:
        message = "Invalid neural capture counter width."
        raise NeuralCaptureRefusalError(message)
    channels = root["channels"]
    if not isinstance(channels, list) or len(channels) != CHANNEL_COUNT:
        message = "Neural capture counter receipt requires three channels."
        raise NeuralCaptureRefusalError(message)
    return (
        _decode_channel(channels[0], "input", bits),
        _decode_channel(channels[1], "state", bits),
        _decode_channel(channels[2], "service", bits),
    )


def reconcile_neural_capture(
    channel: NeuralChannel, counts: NeuralCaptureCounts
) -> NeuralCaptureAccounting:
    """Reconcile decoded original records with a validated actual counter snapshot.

    Parameters
    ----------
    channel
        Original channel export decoded through decode_neural_channel.
    counts
        Typed receipt fields decoded through decode_neural_capture_counts.
        Count wrap and incoherent status snapshots must be excluded by the source.

    Returns
    -------
    NeuralCaptureAccounting
        Original saturation bound and explicit accounting/completeness failures.
        A saturated count is never presented as an exact drop total.
    """
    maximum = (1 << counts.drop_counter_bits) - 1
    saturated = counts.dropped == maximum
    observed = len(channel.events) + len(channel.marker_bytes) // NEURAL_RECORD.size
    refusals = []
    if counts.role != channel.role:
        refusals.append(f"{channel.role}: counter snapshot belongs to another channel")
    difference = counts.attempts - counts.accepted
    if difference < 0 or (
        counts.dropped > difference if saturated else counts.dropped != difference
    ):
        refusals.append(f"{channel.role}: attempted, accepted and dropped counts disagree")
    if counts.overflowed != (counts.dropped > 0):
        refusals.append(f"{channel.role}: overflow flag and drop counter disagree")
    if counts.drained != counts.accepted:
        refusals.append(f"{channel.role}: accepted records were not completely drained")
    if observed != counts.drained:
        refusals.append(f"{channel.role}: exported records differ from drain count")
    if counts.overflowed or counts.dropped:
        refusals.append(f"{channel.role}: capture lost records")
    if saturated:
        refusals.append(f"{channel.role}: drop counter is a lower bound at saturation")
    return NeuralCaptureAccounting(observed, counts.dropped, not saturated, tuple(refusals))
