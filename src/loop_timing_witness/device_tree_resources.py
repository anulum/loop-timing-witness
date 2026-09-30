# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original device-tree register and bus address translation

"""Translate original register extents through their declared ancestor bus ranges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .device_tree_blob import ADDRESS_LIMIT, WORD_BYTES, DeviceTree

if TYPE_CHECKING:
    from .device_tree_structure import Node

MAX_ADDRESS_CELLS = 2


@dataclass(frozen=True)
class Region:
    """One physical or intermediate bus extent, with an exclusive upper bound.

    Parameters
    ----------
    address
        Unsigned start address.
    size
        Declared extent in bytes; CPU identifier registers can have zero size.
    """

    address: int
    size: int


def property_cells(content: bytes) -> tuple[int, ...]:
    """Decode complete big-endian cells without inventing missing words.

    Parameters
    ----------
    content
        Exact property bytes.

    Returns
    -------
    tuple of int
        Original unsigned 32-bit cells in order.

    Raises
    ------
    ValueError
        If the value is not a whole number of cells.
    """
    if len(content) % WORD_BYTES:
        message = "device-tree property is not a whole number of cells"
        raise ValueError(message)
    return tuple(
        int.from_bytes(content[offset : offset + WORD_BYTES], "big")
        for offset in range(0, len(content), WORD_BYTES)
    )


def _count(node: Node, name: str, default: int) -> int:
    """Read an explicit cell count or the standard Devicetree default.

    Parameters
    ----------
    node
        Original parent bus node.
    name
        Address-cell or size-cell property name.
    default
        Standard default for an absent property.

    Returns
    -------
    int
        Single count in the supported RV64 representation.

    Raises
    ------
    ValueError
        If the count is malformed or requires a non-address bus representation.
    """
    value = property_cells(node.properties[name]) if name in node.properties else (default,)
    if len(value) != 1 or value[0] > MAX_ADDRESS_CELLS:
        message = "device-tree bus cell count is unsupported or malformed"
        raise ValueError(message)
    return value[0]


def _number(cells: tuple[int, ...]) -> int:
    """Join original address or size cells without narrowing their integer range.

    Parameters
    ----------
    cells
        Validated consecutive cells for one value.

    Returns
    -------
    int
        Unsigned combined value, or zero for an absent size field.
    """
    value = 0
    for cell in cells:
        value = value << (WORD_BYTES * 8) | cell
    return value


def _translate(tree: DeviceTree, bus_path: str, region: Region) -> Region:
    """Translate one extent through every declared ancestor mapping.

    Parameters
    ----------
    tree
        Original decoded topology.
    bus_path
        Parent bus owning the intermediate address space.
    region
        Whole register extent requiring one unambiguous mapping.

    Returns
    -------
    Region
        Root physical address and unchanged size.

    Raises
    ------
    ValueError
        If ranges are absent, malformed, ambiguous, truncated or fail to cover the extent.
    """
    while bus_path != "/":
        bus = tree.nodes[bus_path]
        parent_path = bus_path.rpartition("/")[0] or "/"
        parent = tree.nodes[parent_path]
        if "ranges" not in bus.properties:
            message = "device-tree bus lacks an address translation"
            raise ValueError(message)
        ranges = property_cells(bus.properties["ranges"])
        child_cells = _count(bus, "#address-cells", 2)
        parent_cells = _count(parent, "#address-cells", 2)
        size_cells = _count(bus, "#size-cells", 1)
        width = child_cells + parent_cells + size_cells
        if not child_cells or not parent_cells or not size_cells or len(ranges) % width:
            message = "device-tree bus ranges have invalid cell geometry"
            raise ValueError(message)
        if ranges:
            candidates = []
            for offset in range(0, len(ranges), width):
                entry = ranges[offset : offset + width]
                child = _number(entry[:child_cells])
                host = _number(entry[child_cells : child_cells + parent_cells])
                size = _number(entry[child_cells + parent_cells :])
                if child <= region.address and region.address + region.size <= child + size:
                    candidates.append(host + region.address - child)
            if len(candidates) != 1:
                message = "device-tree register extent lacks a unique complete bus mapping"
                raise ValueError(message)
            region = Region(candidates[0], region.size)
        if region.address + region.size > 1 << (WORD_BYTES * 8 * parent_cells):
            message = "translated device-tree register exceeds the parent address space"
            raise ValueError(message)
        bus_path = parent_path
    return region


def register_regions(tree: DeviceTree, path: str) -> tuple[Region, ...]:
    """Decode a node's complete reg property and translate it to root addresses.

    Parameters
    ----------
    tree
        Original verified device-tree topology.
    path
        Explicit node path supplied by the platform contract.

    Returns
    -------
    tuple of Region
        Original register extents expressed in root physical address space.

    Raises
    ------
    ValueError
        If the node, property, geometry, bounds or ancestor translation is invalid.
    """
    if path == "/" or path not in tree.nodes or "reg" not in tree.nodes[path].properties:
        message = "device-tree register node or property is absent"
        raise ValueError(message)
    parent_path = path.rpartition("/")[0] or "/"
    parent = tree.nodes[parent_path]
    address_cells = _count(parent, "#address-cells", 2)
    size_cells = _count(parent, "#size-cells", 1)
    values = property_cells(tree.nodes[path].properties["reg"])
    width = address_cells + size_cells
    if not address_cells or not values or len(values) % width:
        message = "device-tree register property has invalid cell geometry"
        raise ValueError(message)
    regions = []
    for offset in range(0, len(values), width):
        entry = values[offset : offset + width]
        region = Region(_number(entry[:address_cells]), _number(entry[address_cells:]))
        if region.address + region.size > min(ADDRESS_LIMIT, 1 << (WORD_BYTES * 8 * address_cells)):
            message = "device-tree register extent exceeds RV64 or declared bus address space"
            raise ValueError(message)
        regions.append(_translate(tree, parent_path, region))
    return tuple(regions)
