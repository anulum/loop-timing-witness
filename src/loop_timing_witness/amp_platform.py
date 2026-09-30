# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original AMP platform resource admission

"""Compose original memory, AXI and PLIC resource bindings before image generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .amp_device import WitnessDevice, bind_device
from .amp_memory import MemorySelection, ReservedMemory, bind_memory
from .device_tree_resources import register_regions

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree
    from .device_tree_interrupts import PlicSelection


@dataclass(frozen=True)
class AmpPlatform:
    """Admitted original resources and explicit dedicated hart/source selection.

    Parameters
    ----------
    memory
        Entire firmware and telemetry reservations.
    device
        Actual AXI aperture and dedicated PLIC register addresses.
    hart
        Explicit hardware hart identifier.
    source
        Explicit original retained interrupt source.
    """

    memory: ReservedMemory
    device: WitnessDevice
    hart: int
    source: int


def bind_platform(
    tree: DeviceTree, memory: MemorySelection, device_path: str, plic: PlicSelection
) -> AmpPlatform:
    """Admit one complete original AMP resource set without claiming runtime ownership.

    Parameters
    ----------
    tree
        Original verified complete platform topology.
    memory
        Explicit original reservations and requested stack/ABI bounds.
    device_path
        Exact original versioned Witness device path.
    plic
        Explicit original interrupt controller, dedicated hart and retained source.

    Returns
    -------
    AmpPlatform
        Immutable resource contract suitable for subsequent compiled ABI/ELF validation.

    Raises
    ------
    ValueError
        If bindings fail or controller registers intersect any original memory bank/reservation.
    """
    admitted_memory = bind_memory(tree, memory)
    device = bind_device(tree, device_path, plic)
    controller = register_regions(tree, plic.path)[0]
    regions = list(register_regions(tree, memory.ram_path))
    regions.extend((admitted_memory.firmware, admitted_memory.shared))
    regions.extend(
        region
        for node in tree.nodes.values()
        if node.properties.get("device_type") == b"memory\0" and node.path != memory.ram_path
        for region in register_regions(tree, node.path)
    )
    if any(
        controller.address < region.address + region.size
        and region.address < controller.address + controller.size
        for region in regions
    ) or any(
        controller.address < address + size and address < controller.address + controller.size
        for address, size in tree.reservations
    ):
        message = "AMP PLIC aperture intersects original RAM or a memory reservation"
        raise ValueError(message)
    return AmpPlatform(admitted_memory, device, plic.hart, plic.source)
