# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original PLIC machine context and register binding

"""Resolve dedicated-hart PLIC registers from actual topology and an explicit layout binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .device_tree_properties import phandle_nodes, single_cell, string_list
from .device_tree_resources import property_cells, register_regions

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree
    from .device_tree_structure import Node

MACHINE_EXTERNAL_IRQ = 11
MAX_SOURCE = 1023
MAX_U54_HART = 4
MAX_CONTEXTS = 15872
UINT32_MAX = (1 << 32) - 1
ENABLE_BASE = 0x2000
ENABLE_STRIDE = 0x80
CONTEXT_BASE = 0x200000
CONTEXT_STRIDE = 0x1000
WORD_BYTES = 4
BITS_PER_WORD = 32


@dataclass(frozen=True)
class PlicSelection:
    """Explicit controller path, U54 hart, device source and admitted concrete layout.

    Parameters
    ----------
    path
        Original DTB PLIC node path.
    hart
        Dedicated U54 hardware identifier, one through four.
    source
        Nonzero original PLIC device interrupt source.
    binding
        Concrete SiFive layout or the actual Spike simulator's legacy layout.
    """

    path: str
    hart: int
    source: int
    binding: Literal["sifive", "spike"]


@dataclass(frozen=True)
class PlicRegisters:
    """Derived physical register addresses for one actual machine context.

    Parameters
    ----------
    context
        Context ordinal in the original interrupts-extended array, including disabled entries.
    priority
        Selected source's priority word.
    enable_word
        Selected context's enable word containing the source bit.
    threshold
        Selected context's priority threshold.
    claim
        Selected context's claim and completion register.
    """

    context: int
    priority: int
    enable_word: int
    threshold: int
    claim: int


def _hart(tree: DeviceTree, controller: Node) -> int:
    """Resolve a CPU interrupt controller to its original hardware CPU identifier.

    Parameters
    ----------
    tree
        Original decoded topology.
    controller
        Phandle-resolved RISC-V CPU interrupt controller.

    Returns
    -------
    int
        Hardware identifier declared by the CPU's reg cells.

    Raises
    ------
    ValueError
        If the reference, compatible, marker, CPU type or CPU cell geometry is invalid.
    """
    if (
        "riscv,cpu-intc" not in string_list(controller, "compatible")
        or single_cell(controller, "#interrupt-cells") != 1
        or controller.properties.get("interrupt-controller") != b""
    ):
        message = "PLIC context does not reference a RISC-V CPU interrupt controller"
        raise ValueError(message)
    cpu_path = controller.path.rpartition("/")[0]
    cpu = tree.nodes.get(cpu_path)
    if cpu is None or cpu.properties.get("device_type") != b"cpu\0":
        message = "PLIC context parent is not an original CPU node"
        raise ValueError(message)
    parent_path = cpu.path.rpartition("/")[0] or "/"
    parent = tree.nodes[parent_path]
    count = single_cell(parent, "#address-cells")
    values = property_cells(cpu.properties.get("reg", b""))
    if count not in (1, 2) or single_cell(parent, "#size-cells") != 0 or len(values) != count:
        message = "PLIC context CPU identifier has invalid cell geometry"
        raise ValueError(message)
    return int.from_bytes(cpu.properties["reg"], "big")


def _context(tree: DeviceTree, plic: Node, hart: int) -> int:
    """Retain every declared context ordinal while locating one unique machine target.

    Parameters
    ----------
    tree
        Original decoded topology.
    plic
        Original PLIC node containing its context reference array.
    hart
        Explicit dedicated hardware identifier.

    Returns
    -------
    int
        Unique original machine context ordinal.

    Raises
    ------
    ValueError
        If references, context geometry, CPU identity or machine-target uniqueness are invalid.
    """
    handles = phandle_nodes(tree)
    cells = property_cells(plic.properties.get("interrupts-extended", b""))
    if not cells or len(cells) % 2 or len(cells) // 2 > MAX_CONTEXTS:
        message = "PLIC context array is empty, incomplete or outside bounds"
        raise ValueError(message)
    candidates = []
    cpu_paths: dict[int, str] = {}
    for offset in range(0, len(cells), 2):
        controller = handles.get(cells[offset])
        if controller is None:
            message = "PLIC context references an undeclared phandle"
            raise ValueError(message)
        identifier = _hart(tree, controller)
        path = controller.path.rpartition("/")[0]
        if identifier in cpu_paths and cpu_paths[identifier] != path:
            message = "PLIC contexts reference multiple CPUs with the same hardware identifier"
            raise ValueError(message)
        cpu_paths[identifier] = path
        interrupt = cells[offset + 1]
        if interrupt not in (9, MACHINE_EXTERNAL_IRQ, UINT32_MAX):
            message = "PLIC context specifies an unsupported CPU interrupt"
            raise ValueError(message)
        if identifier == hart and interrupt == MACHINE_EXTERNAL_IRQ:
            candidates.append(offset // 2)
    if len(candidates) != 1:
        message = "dedicated hart lacks one unique PLIC machine context"
        raise ValueError(message)
    return candidates[0]


def bind_plic(tree: DeviceTree, selection: PlicSelection) -> PlicRegisters:
    """Validate one concrete PLIC binding and derive all dedicated machine register addresses.

    Parameters
    ----------
    tree
        Original admitted DTB bytes decoded without ownership assumptions.
    selection
        Explicit operator request, including the concrete register layout.

    Returns
    -------
    PlicRegisters
        Original-context addresses bounded by the complete declared PLIC aperture.

    Raises
    ------
    ValueError
        If the selection, layout, source, context or complete register extents are invalid.
    """
    if (
        type(selection.hart) is not int
        or type(selection.source) is not int
        or not 1 <= selection.hart <= MAX_U54_HART
        or not 1 <= selection.source <= MAX_SOURCE
        or selection.path not in tree.nodes
    ):
        message = "dedicated PLIC selection is outside the admitted U54/source bounds"
        raise ValueError(message)
    plic = tree.nodes[selection.path]
    compatible = string_list(plic, "compatible")
    binding_ok = (selection.binding == "sifive" and "sifive,plic-1.0.0" in compatible) or (
        selection.binding == "spike"
        and "riscv,plic0" in compatible
        and tree.nodes["/"].properties.get("model") == b"ucbbar,spike-bare\0"
    )
    if not binding_ok:
        message = "PLIC concrete register layout is not bound by the original platform"
        raise ValueError(message)
    if (
        plic.properties.get("interrupt-controller") != b""
        or single_cell(plic, "#interrupt-cells") != 1
        or not selection.source <= single_cell(plic, "riscv,ndev") <= MAX_SOURCE
    ):
        message = "PLIC source or interrupt-controller geometry is invalid"
        raise ValueError(message)
    regions = register_regions(tree, selection.path)
    if len(regions) != 1 or not regions[0].address or regions[0].address % WORD_BYTES:
        message = "PLIC must declare one aligned nonzero physical register aperture"
        raise ValueError(message)
    context = _context(tree, plic, selection.hart)
    offsets = (
        selection.source * WORD_BYTES,
        ENABLE_BASE + context * ENABLE_STRIDE + selection.source // BITS_PER_WORD * WORD_BYTES,
        CONTEXT_BASE + context * CONTEXT_STRIDE,
        CONTEXT_BASE + context * CONTEXT_STRIDE + WORD_BYTES,
    )
    if any(offset + WORD_BYTES > regions[0].size for offset in offsets):
        message = "dedicated PLIC registers exceed the declared aperture"
        raise ValueError(message)
    return PlicRegisters(context, *(regions[0].address + offset for offset in offsets))
