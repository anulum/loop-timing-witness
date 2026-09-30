# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — physical resource and original interrupt consumer collision admission

"""Refuse physical register aliases and duplicate original PLIC source consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .device_tree_properties import phandle_nodes, single_cell
from .device_tree_resources import property_cells, register_regions

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree
    from .device_tree_resources import Region
    from .device_tree_structure import Node

MAX_INTERRUPT_CELLS = 4


def _controller(tree: DeviceTree, node: Node) -> Node:
    """Resolve one inherited original interrupt controller without implicit defaults.

    Parameters
    ----------
    tree
        Original topology with unique global references.
    node
        Original consumer node.

    Returns
    -------
    Node
        Explicitly referenced controller.

    Raises
    ------
    ValueError
        If the inherited controller is absent or undeclared.
    """
    handles = phandle_nodes(tree)
    current = node
    while "interrupt-parent" not in current.properties:
        if current.path == "/":
            message = "interrupt consumer lacks an original parent"
            raise ValueError(message)
        current = tree.nodes[current.path.rpartition("/")[0] or "/"]
    controller = handles.get(single_cell(current, "interrupt-parent"))
    if controller is None:
        message = "interrupt consumer references an undeclared parent"
        raise ValueError(message)
    return controller


def _width(controller: Node) -> int:
    """Require a bounded direct controller specifier rather than an unresolved interrupt nexus.

    Parameters
    ----------
    controller
        Original referenced interrupt controller.

    Returns
    -------
    int
        Original declared interrupt specifier width.

    Raises
    ------
    ValueError
        If the declaration is not a direct supported controller.
    """
    width = single_cell(controller, "#interrupt-cells")
    if (
        controller.properties.get("interrupt-controller") != b""
        or not 1 <= width <= MAX_INTERRUPT_CELLS
    ):
        message = "interrupt consumer requires a bounded direct controller"
        raise ValueError(message)
    return width


def _sources(tree: DeviceTree, node: Node) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Decode every original direct specifier with its actual referenced controller width.

    Parameters
    ----------
    tree
        Original topology and controller references.
    node
        Original consumer, including disabled consumers.

    Returns
    -------
    tuple
        Controller paths and complete original specifiers.

    Raises
    ------
    ValueError
        If forms, references, widths or complete tuples are ambiguous or malformed.
    """
    result = []
    if "interrupts-extended" in node.properties:
        if "interrupts" in node.properties:
            message = "interrupt consumer has ambiguous original forms"
            raise ValueError(message)
        cells = property_cells(node.properties["interrupts-extended"])
        handles = phandle_nodes(tree)
        offset = 0
        while offset < len(cells):
            controller = handles.get(cells[offset])
            if controller is None:
                message = "extended interrupt references an undeclared controller"
                raise ValueError(message)
            width = _width(controller)
            end = offset + 1 + width
            if end > len(cells):
                message = "extended interrupt specifier is truncated"
                raise ValueError(message)
            result.append((controller.path, cells[offset + 1 : end]))
            offset = end
    elif "interrupts" in node.properties:
        controller = _controller(tree, node)
        width = _width(controller)
        cells = property_cells(node.properties["interrupts"])
        if not cells or len(cells) % width:
            message = "interrupt consumer specifier geometry is invalid"
            raise ValueError(message)
        result.extend((controller.path, cells[i : i + width]) for i in range(0, len(cells), width))
    return tuple(result)


def check_collisions(
    tree: DeviceTree, device_path: str, aperture: Region, plic_path: str, source: int
) -> None:
    """Refuse other physical register extents and any other declared selected-source consumer.

    Parameters
    ----------
    tree
        Original admitted topology; disabled resources remain collision candidates.
    device_path
        Exact selected Witness path excluded from other-owner comparisons.
    aperture
        Original complete admitted AXI aperture.
    plic_path
        Original selected PLIC controller path.
    source
        Original selected PLIC source.

    Raises
    ------
    ValueError
        If a mapped physical register extent or direct interrupt consumer conflicts.
    """
    for node in tree.nodes.values():
        if node.path == device_path:
            continue
        if any(
            parent == plic_path and specifier == (source,)
            for parent, specifier in _sources(tree, node)
        ):
            message = "Witness PLIC source has another original consumer"
            raise ValueError(message)
        if "reg" not in node.properties:
            continue
        parent = node.path.rpartition("/")[0] or "/"
        while parent != "/" and "ranges" in tree.nodes[parent].properties:
            parent = parent.rpartition("/")[0] or "/"
        if parent != "/":
            continue
        for region in register_regions(tree, node.path):
            if (
                aperture.address < region.address + region.size
                and region.address < aperture.address + aperture.size
            ):
                message = "Witness AXI aperture overlaps another original physical resource"
                raise ValueError(message)

    if any(
        aperture.address < address + size and address < aperture.address + aperture.size
        for address, size in tree.reservations
    ):
        message = "Witness AXI aperture overlaps an original header reservation"
        raise ValueError(message)
