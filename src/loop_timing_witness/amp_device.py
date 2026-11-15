# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original AXI aperture and retained interrupt resource binding

"""Bind the declared Witness AXI device to one original PLIC interrupt source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .amp_collisions import check_collisions
from .device_tree_interrupts import PlicRegisters, PlicSelection, bind_plic
from .device_tree_properties import phandle_nodes, single_cell, string_list
from .device_tree_resources import Region, property_cells, register_regions

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree
    from .device_tree_structure import Node

COMPATIBLE = "anulum,loop-timing-witness-axi-v1"
APERTURE_BYTES = 256
EXTENDED_INTERRUPT_CELLS = 2


@dataclass(frozen=True)
class WitnessDevice:
    """Original physical AXI aperture and dedicated machine PLIC registers.

    Parameters
    ----------
    aperture
        Complete 256-byte physical AXI aperture.
    plic
        Original source and machine-context register addresses.
    """

    aperture: Region
    plic: PlicRegisters


def _parent(tree: DeviceTree, node: Node) -> Node:
    """Resolve the declared inherited interrupt-parent to one original controller.

    Parameters
    ----------
    tree
        Original complete topology.
    node
        Interrupt consumer whose parent is being resolved.

    Returns
    -------
    Node
        Original referenced controller.

    Raises
    ------
    ValueError
        If no inherited parent exists or its reference is undeclared.
    """
    handles = phandle_nodes(tree)
    current = node
    while True:
        if "interrupt-parent" in current.properties:
            controller = handles.get(single_cell(current, "interrupt-parent"))
            if controller is None:
                message = "interrupt-parent references an undeclared controller"
                raise ValueError(message)
            return controller
        if current.path == "/":
            message = "device lacks an original interrupt-parent"
            raise ValueError(message)
        current = tree.nodes[current.path.rpartition("/")[0] or "/"]


def _interrupt(tree: DeviceTree, node: Node) -> tuple[Node | None, int]:
    """Return the interrupt parent and source the device node declares.

    Parameters
    ----------
    tree
        Original verified topology.
    node
        Witness device node.

    Returns
    -------
    tuple[Node | None, int]
        Parent controller node, if its phandle resolves, and the source number.

    Raises
    ------
    ValueError
        If both interrupt forms are declared or the extended form is not one interrupt.
    """
    if "interrupts-extended" not in node.properties:
        return _parent(tree, node), single_cell(node, "interrupts")
    if "interrupts" in node.properties or "interrupt-parent" in node.properties:
        message = "Witness interrupt declaration is ambiguous"
        raise ValueError(message)
    cells = property_cells(node.properties["interrupts-extended"])
    if len(cells) != EXTENDED_INTERRUPT_CELLS:
        message = "Witness requires exactly one original PLIC interrupt"
        raise ValueError(message)
    return phandle_nodes(tree).get(cells[0]), cells[1]


def _aperture(tree: DeviceTree, path: str, selection: PlicSelection) -> Region:
    """Return the device's one aligned 256-byte aperture, apart from the PLIC.

    Parameters
    ----------
    tree
        Original verified topology.
    path
        Witness device node path.
    selection
        Selected PLIC layout.

    Returns
    -------
    Region
        The AXI aperture.

    Raises
    ------
    ValueError
        If the device does not have exactly one aligned complete aperture, or it
        overlaps the PLIC registers.
    """
    regions = register_regions(tree, path)
    if (
        len(regions) != 1
        or not regions[0].address
        or regions[0].address % APERTURE_BYTES
        or regions[0].size != APERTURE_BYTES
    ):
        message = "Witness requires one aligned complete 256-byte AXI aperture"
        raise ValueError(message)
    aperture = regions[0]
    controller = register_regions(tree, selection.path)[0]
    if (
        aperture.address < controller.address + controller.size
        and controller.address < aperture.address + aperture.size
    ):
        message = "Witness AXI aperture overlaps the PLIC"
        raise ValueError(message)
    return aperture


def bind_device(tree: DeviceTree, path: str, selection: PlicSelection) -> WitnessDevice:
    """Bind one explicit versioned AXI aperture and retained source to its actual PLIC.

    Parameters
    ----------
    tree
        Original verified topology, with the actual plugin declaration included for ISA runs.
    path
        Explicit Witness device node path.
    selection
        Explicit dedicated hart, source and concrete PLIC layout.

    Returns
    -------
    WitnessDevice
        Original physical resources; Linux/HSS/PMP ownership remains separately admitted.

    Raises
    ------
    ValueError
        If device identity, status, interrupt wiring or aperture is invalid or conflicts with PLIC.
    """
    node = tree.nodes.get(path)
    if (
        node is None
        or node.properties.get("status", b"okay\0") not in (b"okay\0", b"ok\0")
        or COMPATIBLE not in string_list(node, "compatible")
    ):
        message = "Witness requires an enabled original versioned AXI device node"
        raise ValueError(message)
    parent, source = _interrupt(tree, node)
    if parent is None or parent.path != selection.path or source != selection.source:
        message = "Witness interrupt does not match the selected PLIC and source"
        raise ValueError(message)
    plic = bind_plic(tree, selection)
    aperture = _aperture(tree, path, selection)
    check_collisions(tree, path, aperture, selection.path, selection.source)
    return WitnessDevice(aperture, plic)
