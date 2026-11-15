# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — neural channel record decoding and original-byte projections

"""Decode separate neural capture channels without concealing missing observations."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Final

NEURAL_RECORD: Final = struct.Struct("<BBHIQ")
ALIGNMENT_MARKER_CODE: Final = 17
MAX_CHANNEL_POPULATION: Final = 1000
ENCODER_TICK_LIMIT: Final = 1 << 16


class NeuralCaptureRefusalError(ValueError):
    """An authored refusal of neural capture bytes or their declared population."""


@dataclass(frozen=True, slots=True)
class NeuralEvent:
    """One original channel observation.

    Attributes
    ----------
    identity
        Original step index or encoder packet ordinal, never reassigned after loss.
    ticks
        Original shared capture-counter value in simulator edges.
    """

    identity: int
    ticks: int


@dataclass(frozen=True, slots=True)
class NeuralChannel:
    """Decoded observations and exact projections of one raw channel.

    Attributes
    ----------
    role
        Declared input, state or service channel.
    events
        Original ordered observations, retaining identity gaps.
    start_tick, end_tick
        Dedicated alignment-marker ticks, or None when the marker is absent.
        Marker presence does not establish complete finalisation or validity.
    payload_bytes
        Original data records concatenated without markers or re-encoding.
    marker_bytes
        Original marker records in capture order, without re-encoding.
    """

    role: str
    events: tuple[NeuralEvent, ...]
    start_tick: int | None
    end_tick: int | None
    payload_bytes: bytes
    marker_bytes: bytes


def _validate_channel_arguments(content: bytes, role: str, identity_limit: int) -> int:
    """Check channel selection, finite population and binary record framing.

    Parameters
    ----------
    content
        Original raw channel bytes.
    role
        Input, state or service role.
    identity_limit
        Exclusive population bound; zero is meaningful for service only.

    Returns
    -------
    int
        The role's required data-record code.

    Raises
    ------
    NeuralCaptureRefusalError
        If a declared argument violates the channel contract.
    """
    if role not in ("input", "state", "service"):
        message = "Unknown neural capture channel role."
        raise NeuralCaptureRefusalError(message)
    if (
        type(identity_limit) is not int
        or not 0 <= identity_limit <= MAX_CHANNEL_POPULATION
        or (identity_limit == 0 and role != "service")
    ):
        message = "Invalid neural capture population."
        raise NeuralCaptureRefusalError(message)
    if type(content) is not bytes or len(content) % NEURAL_RECORD.size:
        message = "Neural capture is not a whole sequence of 16-byte records."
        raise NeuralCaptureRefusalError(message)
    return {"input": 14, "state": 15, "service": 16}[role]


@dataclass(slots=True)
class _ChannelDecoder:
    """Running decode of one channel's records, in capture order.

    Attributes
    ----------
    content
        Original raw channel bytes.
    data_code, identity_limit
        The role's data-record code and its exclusive identity bound.
    events, payload, markers
        Observations, data records and marker records decoded so far.
    start_tick, end_tick
        Alignment-marker ticks, or ``None`` while absent.
    previous_tick, previous_identity
        Last accepted tick and data identity; ``-1`` before the first.
    """

    content: bytes
    data_code: int
    identity_limit: int
    events: list[NeuralEvent] = field(default_factory=list)
    payload: list[bytes] = field(default_factory=list)
    markers: list[bytes] = field(default_factory=list)
    start_tick: int | None = None
    end_tick: int | None = None
    previous_tick: int = -1
    previous_identity: int = -1

    def record(self, offset: int) -> None:
        """Decode the record at one offset and keep its original bytes.

        Parameters
        ----------
        offset
            Byte offset of a whole record.

        Raises
        ------
        NeuralCaptureRefusalError
            If reserved bits are set, the tick does not advance within the
            horizon, or the record is a misplaced marker or an unordered or
            foreign data record.
        """
        code, reserved_byte, reserved_word, identity, ticks = NEURAL_RECORD.unpack_from(
            self.content, offset
        )
        if reserved_byte or reserved_word:
            message = "Neural capture reserved bits must be zero."
            raise NeuralCaptureRefusalError(message)
        if ticks >= ENCODER_TICK_LIMIT or ticks <= self.previous_tick:
            message = "Neural capture ticks regress, repeat or exceed the no-wrap horizon."
            raise NeuralCaptureRefusalError(message)
        self.previous_tick = ticks
        original = self.content[offset : offset + NEURAL_RECORD.size]
        if code == ALIGNMENT_MARKER_CODE:
            self._marker(identity, offset, ticks)
            self.markers.append(original)
            return
        if code != self.data_code:
            message = "Neural capture contains a code from another channel or profile."
            raise NeuralCaptureRefusalError(message)
        if identity >= self.identity_limit or identity <= self.previous_identity:
            message = "Neural capture identities repeat, regress or exceed the population."
            raise NeuralCaptureRefusalError(message)
        self.previous_identity = identity
        self.events.append(NeuralEvent(identity, ticks))
        self.payload.append(original)

    def _marker(self, identity: int, offset: int, ticks: int) -> None:
        """Accept a start marker as the first record or an end marker as the last.

        Parameters
        ----------
        identity, offset, ticks
            Marker identity, byte offset and tick.

        Raises
        ------
        NeuralCaptureRefusalError
            If the marker has another identity or position.
        """
        if identity == 0 and offset == 0:
            self.start_tick = ticks
        elif identity == 1 and offset + NEURAL_RECORD.size == len(self.content):
            self.end_tick = ticks
        else:
            message = "Neural alignment marker has an invalid identity or position."
            raise NeuralCaptureRefusalError(message)


def decode_neural_channel(content: bytes, role: str, identity_limit: int) -> NeuralChannel:
    """Validate a neural channel and preserve its original records and gaps.

    Parameters
    ----------
    content
        Exact bytes already verified against the run's capture-file reference.
    role
        Input, state or service, selecting data code 14, 15 or 16 respectively.
        Code 17 denotes the dedicated start and end alignment markers.
    identity_limit
        Exclusive bound on the declared step or packet population, at most 1,000.
        Zero is allowed only for a service channel with no expected packets.

    Returns
    -------
    NeuralChannel
        Actual events and original payload/marker byte projections. Missing
        markers, missing identities and an empty channel remain observable;
        the complete run verifier must refuse them when required by its scope.

    Raises
    ------
    NeuralCaptureRefusalError
        If the role, population, byte layout, code, reserved bits, marker
        position, identity order or tick order contradict the channel contract.
    """
    decoder = _ChannelDecoder(
        content, _validate_channel_arguments(content, role, identity_limit), identity_limit
    )
    for offset in range(0, len(content), NEURAL_RECORD.size):
        decoder.record(offset)
    return NeuralChannel(
        role,
        tuple(decoder.events),
        decoder.start_tick,
        decoder.end_tick,
        b"".join(decoder.payload),
        b"".join(decoder.markers),
    )
