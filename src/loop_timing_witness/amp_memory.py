# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original dedicated firmware and telemetry RAM reservations

"""Admit explicit disjoint reserved-memory extents before compiling the AMP image."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .device_tree_properties import single_cell
from .device_tree_resources import Region, register_regions

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree

PAGE_BYTES = 4096
STACK_ALIGNMENT = 16
RESERVED_ROOT = "/reserved-memory"


@dataclass(frozen=True)
class MemorySelection:
    """Explicit original RAM and reserved-node paths plus requested compile-time bounds.

    Parameters
    ----------
    ram_path
        Original system RAM node containing both entire reservations.
    firmware_path
        Direct reserved-memory child assigned to this firmware image and stack.
    shared_path
        Different direct reserved-memory child assigned to the telemetry owners.
    mailbox_bytes
        Minimum telemetry ABI capacity; the image builder also checks actual C sizeof.
    stack_bytes
        Explicit integer-only firmware stack allocation.
    """

    ram_path: str
    firmware_path: str
    shared_path: str
    mailbox_bytes: int
    stack_bytes: int


@dataclass(frozen=True)
class ReservedMemory:
    """Original physical image and telemetry reservations, without runtime ownership claims.

    Parameters
    ----------
    firmware
        Entire admitted image and stack reservation.
    shared
        Entire admitted telemetry reservation.
    """

    firmware: Region
    shared: Region


def _parent(tree: DeviceTree) -> None:
    """Validate the original reserved-memory parent's root-compatible identity geometry.

    Parameters
    ----------
    tree
        Original decoded topology.

    Raises
    ------
    ValueError
        If the parent, required empty translation or cell-count agreement is invalid.
    """
    parent = tree.nodes.get(RESERVED_ROOT)
    if parent is None or parent.properties.get("ranges") != b"":
        message = "reserved-memory parent requires an explicit empty ranges property"
        raise ValueError(message)
    root = tree.nodes["/"]
    for name, default in (("#address-cells", 2), ("#size-cells", 1)):
        expected = single_cell(root, name) if name in root.properties else default
        if single_cell(parent, name) != expected:
            message = "reserved-memory cell geometry differs from the original root"
            raise ValueError(message)


def _reservation(tree: DeviceTree, path: str) -> Region:
    """Require one fixed page-aligned unmapped non-reusable original reservation.

    Parameters
    ----------
    tree
        Original decoded topology.
    path
        Explicit direct child of reserved-memory.

    Returns
    -------
    Region
        Original complete physical reservation.

    Raises
    ------
    ValueError
        If path, status, mapping marker, reuse flag or complete extent is invalid.
    """
    node = tree.nodes.get(path)
    if node is None or path.rpartition("/")[0] != RESERVED_ROOT:
        message = "AMP reservation must be an original direct reserved-memory child"
        raise ValueError(message)
    if (
        node.properties.get("no-map") != b""
        or "reusable" in node.properties
        or node.properties.get("status", b"okay\0") not in (b"okay\0", b"ok\0")
    ):
        message = "AMP reservation must be enabled, unmapped and non-reusable"
        raise ValueError(message)
    regions = register_regions(tree, path)
    if (
        len(regions) != 1
        or not regions[0].address
        or not regions[0].size
        or regions[0].address % PAGE_BYTES
        or regions[0].size % PAGE_BYTES
    ):
        message = "AMP reservation must declare one nonzero page-aligned extent"
        raise ValueError(message)
    return regions[0]


def _collisions(tree: DeviceTree, memory: ReservedMemory, paths: tuple[str, str]) -> None:
    """Reject other original reservations intersecting either complete owned extent.

    Parameters
    ----------
    tree
        Original decoded topology and header reservation map.
    memory
        Complete candidate reservations, already checked for mutual overlap.
    paths
        Exact selected reserved-node paths excluded from other-owner checks.

    Raises
    ------
    ValueError
        If another reserved node or an unmatched header reservation overlaps a candidate.
    """
    owners = (memory.firmware, memory.shared)
    for node in tree.nodes.values():
        if node.path in paths or node.path.rpartition("/")[0] != RESERVED_ROOT:
            continue
        for other in register_regions(tree, node.path):
            if any(
                owner.address < other.address + other.size
                and other.address < owner.address + owner.size
                for owner in owners
            ):
                message = "AMP memory intersects another reserved-memory node"
                raise ValueError(message)
    for address, size in tree.reservations:
        other = Region(address, size)
        if other in owners:
            continue
        if any(
            owner.address < address + size and address < owner.address + owner.size
            for owner in owners
        ):
            message = "AMP memory intersects an unmatched original header reservation"
            raise ValueError(message)


def _reject_other_ram_alias(tree: DeviceTree, memory: ReservedMemory, selected_path: str) -> None:
    """Reject another declared RAM node intersecting either owned reservation.

    Parameters
    ----------
    tree
        Complete original decoded topology.
    memory
        Selected firmware and telemetry reservations.
    selected_path
        Exact backing RAM node already checked for complete coverage.

    Raises
    ------
    ValueError
        If another declared RAM bank aliases either selected extent.
    """
    for node in tree.nodes.values():
        if node.path == selected_path or node.properties.get("device_type") != b"memory\0":
            continue
        for other in register_regions(tree, node.path):
            if any(
                owner.address < other.address + other.size
                and other.address < owner.address + owner.size
                for owner in (memory.firmware, memory.shared)
            ):
                message = f"AMP reservation has ambiguous original RAM ownership: {node.path}"
                raise ValueError(message)


def bind_memory(tree: DeviceTree, selection: MemorySelection) -> ReservedMemory:
    """Validate entire image/shared reservations and explicit requested ABI and stack bounds.

    Parameters
    ----------
    tree
        Original verified binary device-tree topology.
    selection
        Explicit resource paths and build bounds; no board-address defaults.

    Returns
    -------
    ReservedMemory
        Disjoint entire reserved extents fitting unambiguously in declared system RAM.

    Raises
    ------
    ValueError
        If selected resources, bounds, RAM coverage or another declared memory region conflict.
    """
    if (
        selection.firmware_path == selection.shared_path
        or type(selection.mailbox_bytes) is not int
        or selection.mailbox_bytes <= 0
        or type(selection.stack_bytes) is not int
        or selection.stack_bytes < PAGE_BYTES
        or selection.stack_bytes % STACK_ALIGNMENT
    ):
        message = "AMP memory selection or requested ABI/stack bounds are invalid"
        raise ValueError(message)
    _parent(tree)
    memory = ReservedMemory(
        _reservation(tree, selection.firmware_path), _reservation(tree, selection.shared_path)
    )
    if (
        memory.firmware.address < memory.shared.address + memory.shared.size
        and memory.shared.address < memory.firmware.address + memory.firmware.size
    ):
        message = "entire firmware and telemetry reservations overlap"
        raise ValueError(message)
    if selection.mailbox_bytes > memory.shared.size or selection.stack_bytes > memory.firmware.size:
        message = "requested telemetry ABI or stack exceeds its original reservation"
        raise ValueError(message)
    ram = tree.nodes.get(selection.ram_path)
    if (
        ram is None
        or ram.properties.get("device_type") != b"memory\0"
        or ram.properties.get("status", b"okay\0") not in (b"okay\0", b"ok\0")
    ):
        message = "AMP backing RAM must be an enabled original memory node"
        raise ValueError(message)
    banks = register_regions(tree, selection.ram_path)
    for owner in (memory.firmware, memory.shared):
        covering = [
            bank
            for bank in banks
            if bank.address <= owner.address
            and owner.address + owner.size <= bank.address + bank.size
        ]
        if len(covering) != 1:
            message = "AMP reservation lacks one complete unambiguous original RAM bank"
            raise ValueError(message)
    _reject_other_ram_alias(tree, memory, selection.ram_path)
    _collisions(tree, memory, (selection.firmware_path, selection.shared_path))
    return memory
