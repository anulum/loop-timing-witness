# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — admitted binary device-tree blocks and memory reservations

"""Read bounded version-17-compatible DTB bytes before binding AMP resources."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .device_tree_structure import Node, decode_structure

MAGIC = 0xD00DFEED
HEADER_SIZE = 40
WORD_BYTES = 4
RESERVATION_SIZE = 16
RESERVATION_ALIGNMENT = 8
VERSION = 17
MAX_BLOB_BYTES = 16 * 1024 * 1024
ADDRESS_LIMIT = 1 << 64


@dataclass(frozen=True)
class DeviceTree:
    """Decoded topology and exact header reservations without ownership claims.

    Parameters
    ----------
    nodes
        Absolute node paths and their uninterpreted properties.
    reservations
        Nonoverlapping physical address and size pairs from the reservation map.
    boot_cpu
        Physical CPU identifier declared by the original header.
    """

    nodes: dict[str, Node]
    reservations: tuple[tuple[int, int], ...]
    boot_cpu: int


def _reservations(data: bytes, offset: int, limit: int) -> tuple[tuple[tuple[int, int], ...], int]:
    """Read the bounded reservation map and reject overlapping physical extents.

    Parameters
    ----------
    data
        Entire verified-size blob.
    offset
        Aligned start of the reservation map.
    limit
        First following block offset, or total blob size.

    Returns
    -------
    tuple
        Reservation pairs and offset after the terminating zero pair.

    Raises
    ------
    ValueError
        If the map is truncated, unterminated, overlapping or outside RV64 space.
    """
    entries: list[tuple[int, int]] = []
    while offset + RESERVATION_SIZE <= limit:
        address = int.from_bytes(data[offset : offset + RESERVATION_ALIGNMENT], "big")
        size = int.from_bytes(
            data[offset + RESERVATION_ALIGNMENT : offset + RESERVATION_SIZE], "big"
        )
        offset += RESERVATION_SIZE
        if address == 0 and size == 0:
            ordered = sorted(entries)
            for previous, current in pairwise(ordered):
                if previous[0] + previous[1] > current[0]:
                    message = "overlapping device-tree memory reservations"
                    raise ValueError(message)
            return tuple(entries), offset
        if size == 0 or address + size > ADDRESS_LIMIT:
            message = "device-tree memory reservation outside RV64 address space"
            raise ValueError(message)
        entries.append((address, size))
    message = "device-tree memory reservation map lacks its terminator"
    raise ValueError(message)


def decode_device_tree(content: bytes) -> DeviceTree:
    """Validate actual DTB headers, block extents, reservations and token structure.

    Parameters
    ----------
    content
        Exact original DTB file bytes, including declared padding.

    Returns
    -------
    DeviceTree
        Decoded nodes, memory reservations and original boot CPU identifier.

    Raises
    ------
    ValueError
        If size, magic, version, alignment, block separation or contents are invalid.
    """
    if not HEADER_SIZE <= len(content) <= MAX_BLOB_BYTES:
        message = "device-tree blob size outside admitted bounds"
        raise ValueError(message)
    words = [
        int.from_bytes(content[offset : offset + WORD_BYTES], "big")
        for offset in range(0, HEADER_SIZE, WORD_BYTES)
    ]
    (
        magic,
        total,
        structure,
        strings,
        reserved,
        version,
        compatible,
        boot_cpu,
        string_size,
        structure_size,
    ) = words
    if (
        magic != MAGIC
        or total != len(content)
        or version < VERSION
        or compatible > VERSION
        or compatible > version
    ):
        message = "invalid device-tree magic, total size or compatible version"
        raise ValueError(message)
    blocks = [(structure, structure + structure_size), (strings, strings + string_size)]
    if (
        structure % WORD_BYTES
        or structure_size % WORD_BYTES
        or not structure_size
        or reserved % RESERVATION_ALIGNMENT
        or reserved < HEADER_SIZE
        or reserved >= total
        or any(start < HEADER_SIZE or end > total for start, end in blocks)
        or (blocks[0][0] < blocks[1][1] and blocks[1][0] < blocks[0][1])
        or any(start <= reserved < end for start, end in blocks)
    ):
        message = "invalid device-tree block alignment, bounds or overlap"
        raise ValueError(message)
    limit = min([total, *(start for start, _ in blocks if start > reserved)])
    reservations, _ = _reservations(content, reserved, limit)
    nodes = decode_structure(
        content[structure : structure + structure_size], content[strings : strings + string_size]
    )
    return DeviceTree(nodes, reservations, boot_cpu)
