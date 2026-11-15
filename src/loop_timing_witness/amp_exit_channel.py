# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original target-produced ISA completion channel admission

"""Refuse incompatible exit modes and preloaded completion in original firmware images."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .amp_elf import READ_WRITE
from .amp_elf_symbols import read_symbols

if TYPE_CHECKING:
    from .amp_elf import LoadSegment
    from .amp_elf_symbols import ElfSymbol

CHANNEL_BYTES = 8
CHANNEL_ALIGNMENT = 64
OBJECT_KIND = 1


def _channel_address(content: bytes, segments: tuple[LoadSegment, ...], symbol: ElfSymbol) -> int:
    """Return one completion channel's address after checking its word and initial bytes.

    Parameters
    ----------
    content
        Complete original firmware.
    segments
        Admitted load segments.
    symbol
        Channel symbol.

    Returns
    -------
    int
        The channel's address.

    Raises
    ------
    ValueError
        If the channel is not one aligned object word in exactly one writable
        segment's file bytes, or those bytes are not zero.
    """
    owners = [
        segment
        for segment in segments
        if segment.flags == READ_WRITE
        and segment.address <= symbol.address
        and symbol.address + symbol.size <= segment.address + segment.file_bytes
    ]
    if (
        symbol.kind != OBJECT_KIND
        or symbol.size != CHANNEL_BYTES
        or symbol.address % CHANNEL_ALIGNMENT
        or len(owners) != 1
    ):
        message = "ISA completion channel must be one aligned writable original word"
        raise ValueError(message)
    offset = owners[0].offset + symbol.address - owners[0].address
    if content[offset : offset + CHANNEL_BYTES] != bytes(CHANNEL_BYTES):
        message = "ISA completion channel cannot be preloaded before target execution"
        raise ValueError(message)
    return symbol.address


def admit_exit_channel(content: bytes, segments: tuple[LoadSegment, ...], *, isa: bool) -> None:
    """Require two distinct initially zero writable HTIF words only for actual ISA images.

    Parameters
    ----------
    content
        Original fully admitted firmware ELF bytes.
    segments
        Original complete bounded load extents.
    isa
        True for actual target HTIF completion, false for the parked board exit.

    Raises
    ------
    ValueError
        If original exit symbols, backing, alignment or initialized values contradict the mode.
    """
    symbols = read_symbols(content)
    names = ("tohost", "fromhost")
    if not isa:
        if any(name in symbols for name in names):
            message = "parked firmware cannot declare an ISA completion channel"
            raise ValueError(message)
        return
    if any(name not in symbols for name in names):
        message = "ISA firmware requires both original HTIF completion channel symbols"
        raise ValueError(message)
    addresses = [_channel_address(content, segments, symbols[name]) for name in names]
    if addresses[0] == addresses[1]:
        message = "ISA completion channels must have distinct original addresses"
        raise ValueError(message)
