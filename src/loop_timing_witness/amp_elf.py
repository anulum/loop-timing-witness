# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded original RV64 executable load-segment admission

"""Validate original RV64 ELF load extents before admitting a firmware image."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .device_tree_resources import Region

ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_PROGRAM_HEADERS = 128
RV64_MACHINE = 243
EXECUTABLE_TYPE = 2
LOAD_TYPE = 1
FORBIDDEN_TYPES = (2, 3)
READ_EXECUTE = 5
READ_WRITE = 6
RVC_FLAG = 1
PAGE_BYTES = 4096
ADDRESS_LIMIT = 1 << 64


@dataclass(frozen=True)
class LoadSegment:
    """One original complete loadable file and physical memory extent.

    Parameters
    ----------
    offset
        Original file byte offset.
    address
        Identical original virtual and physical load address.
    file_bytes
        Original initialized bytes to load.
    memory_bytes
        Whole initialized plus zero-filled extent.
    flags
        Exact RX or RW ELF permission bits.
    """

    offset: int
    address: int
    file_bytes: int
    memory_bytes: int
    flags: int


def _geometry(content: bytes, reservation: Region) -> tuple[int, int]:
    """Validate original executable identity and return bounded program table geometry.

    Parameters
    ----------
    content
        Entire original ELF image.
    reservation
        Admitted firmware RAM extent and required entry address.

    Returns
    -------
    tuple of int
        Original program table offset and entry count.

    Raises
    ------
    ValueError
        If original executable identity or table geometry violates the firmware contract.
    """
    if not ELF_HEADER.size <= len(content) <= MAX_IMAGE_BYTES:
        message = "firmware ELF image size is outside bounds"
        raise ValueError(message)
    ident, kind, machine, version, entry, phoff, _, flags, ehsize, phsize, phcount, _, _, _ = (
        ELF_HEADER.unpack_from(content)
    )
    if (
        ident[:7] != b"\x7fELF\x02\x01\x01"
        or ident[7] != 0
        or kind != EXECUTABLE_TYPE
        or machine != RV64_MACHINE
        or version != 1
        or flags & ~RVC_FLAG
    ):
        message = "firmware requires a static little-endian soft-float RV64 executable"
        raise ValueError(message)
    if (
        ehsize != ELF_HEADER.size
        or phsize != PROGRAM_HEADER.size
        or not 1 <= phcount <= MAX_PROGRAM_HEADERS
        or phoff < ELF_HEADER.size
        or phoff + phcount * phsize > len(content)
        or entry != reservation.address
    ):
        message = "firmware ELF header geometry or entry differs from the reservation"
        raise ValueError(message)
    return phoff, phcount


def admit_elf(content: bytes, reservation: Region) -> tuple[LoadSegment, ...]:
    """Admit original static little-endian soft-float RV64 segments inside reserved RAM.

    Parameters
    ----------
    content
        Entire original compiler/linker-produced ELF image.
    reservation
        Entire admitted firmware and stack reservation.

    Returns
    -------
    tuple of LoadSegment
        Complete original load segments, with the entry backed by executable file bytes.

    Raises
    ------
    ValueError
        If identity, header geometry, loader semantics, permissions or extents are invalid.
    """
    phoff, phcount = _geometry(content, reservation)
    entry = reservation.address
    segments: list[LoadSegment] = []
    for index in range(phcount):
        kind, permissions, offset, virtual, physical, file_bytes, memory_bytes, alignment = (
            PROGRAM_HEADER.unpack_from(content, phoff + index * PROGRAM_HEADER.size)
        )
        if kind in FORBIDDEN_TYPES:
            message = "firmware ELF cannot require a dynamic loader or interpreter"
            raise ValueError(message)
        if offset + file_bytes > len(content):
            message = "firmware ELF program file extent is truncated"
            raise ValueError(message)
        if kind != LOAD_TYPE:
            continue
        if (
            permissions not in (READ_EXECUTE, READ_WRITE)
            or not memory_bytes
            or file_bytes > memory_bytes
            or virtual != physical
            or alignment < PAGE_BYTES
            or alignment & (alignment - 1)
            or offset % alignment != physical % alignment
            or physical + memory_bytes > ADDRESS_LIMIT
            or physical < reservation.address
            or physical + memory_bytes > reservation.address + reservation.size
        ):
            message = "firmware ELF load segment violates permissions, geometry or reserved RAM"
            raise ValueError(message)
        segment = LoadSegment(offset, physical, file_bytes, memory_bytes, permissions)
        for prior in segments:
            if (
                physical < prior.address + prior.memory_bytes
                and prior.address < physical + memory_bytes
            ) or (
                file_bytes
                and prior.file_bytes
                and offset < prior.offset + prior.file_bytes
                and prior.offset < offset + file_bytes
            ):
                message = "firmware ELF load segments overlap in memory or file"
                raise ValueError(message)
        segments.append(segment)
    if not any(
        segment.flags == READ_EXECUTE
        and segment.address <= entry < segment.address + segment.file_bytes
        for segment in segments
    ):
        message = "firmware ELF entry lacks original executable file bytes"
        raise ValueError(message)
    return tuple(segments)
