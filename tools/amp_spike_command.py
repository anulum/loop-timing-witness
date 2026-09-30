# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original Spike hart context and bounded target execution arguments

"""Bind actual Spike process arguments to original hart and PLIC context declarations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from amp_memory import PAGE_BYTES
from device_tree_properties import phandle_nodes, single_cell, string_list
from device_tree_resources import property_cells, register_regions

if TYPE_CHECKING:
    from pathlib import Path

    from amp_platform import AmpPlatform
    from device_tree_blob import DeviceTree
    from device_tree_resources import Region

ISA = "rv64imac_zicsr_zifencei"
MAX_HART = 4
MAX_RTC_NANOSECONDS = 1000000
MIN_TIME_LIMIT = 1000000
UINT64_MAX = (1 << 64) - 1


@dataclass(frozen=True)
class SpikeTools:
    """Explicit installed simulator and actual plugin with functional clock bounds.

    Parameters
    ----------
    executable
        Actual executable Spike path.
    plugin
        Actual compiled Witness AXI plugin path.
    rtc_nanoseconds
        Explicit functional simulator RTC tick mapping, not a physical timing measurement.
    time_limit
        Actual plugin's simulated nanosecond safety limit.
    """

    executable: Path
    plugin: Path
    rtc_nanoseconds: int
    time_limit: int


@dataclass(frozen=True)
class SpikePaths:
    """Explicit executable image snapshot and exclusive actual capture output.

    Parameters
    ----------
    image
        Admitted firmware, DTB and configuration snapshot directory.
    output
        Actual exclusive event and tracking output directory.
    """

    image: Path
    output: Path


def original_harts(tree: DeviceTree, plic_path: str) -> tuple[int, ...]:
    """Require original Spike machine/supervisor contexts to match every sorted original CPU.

    Parameters
    ----------
    tree
        Complete original admitted DTB for the actual ISA process.
    plic_path
        Original actual Spike PLIC path.

    Returns
    -------
    tuple of int
        Unique original hardware identifiers in actual Spike context allocation order.

    Raises
    ------
    ValueError
        If model, CPU identity/ISA/geometry or exact original M/S context order is incompatible.
    """
    if tree.nodes["/"].properties.get("model") != b"ucbbar,spike-bare\0":
        message = "Spike execution requires the original simulator model declaration"
        raise ValueError(message)
    handles = phandle_nodes(tree)
    controllers = {}
    for cpu in tree.nodes.values():
        if cpu.properties.get("device_type") != b"cpu\0":
            continue
        parent = tree.nodes[cpu.path.rpartition("/")[0] or "/"]
        cells = property_cells(cpu.properties.get("reg", b""))
        count = single_cell(parent, "#address-cells")
        if count not in (1, 2) or len(cells) != count or single_cell(parent, "#size-cells") != 0:
            message = "Spike original CPU identifier geometry is invalid"
            raise ValueError(message)
        identifier = int.from_bytes(cpu.properties["reg"], "big")
        if (
            identifier > MAX_HART
            or identifier in controllers
            or cpu.properties.get("status", b"okay\0") not in (b"okay\0", b"ok\0")
            or cpu.properties.get("riscv,isa") != ISA.encode("ascii") + b"\0"
        ):
            message = "Spike original CPU identity, status or ISA is incompatible"
            raise ValueError(message)
        matches = [
            handle
            for handle, node in handles.items()
            if node.path.rpartition("/")[0] == cpu.path
            and "riscv,cpu-intc" in string_list(node, "compatible")
            and node.properties.get("interrupt-controller") == b""
            and single_cell(node, "#interrupt-cells") == 1
        ]
        if len(matches) != 1:
            message = "Spike CPU requires one original referenced interrupt controller"
            raise ValueError(message)
        controllers[identifier] = matches[0]
    if not controllers:
        message = "Spike topology has no original enabled CPUs"
        raise ValueError(message)
    harts = tuple(sorted(controllers))
    expected = tuple(
        cell for hart in harts for cell in (controllers[hart], 11, controllers[hart], 9)
    )
    plic = tree.nodes.get(plic_path)
    if plic is None or property_cells(plic.properties.get("interrupts-extended", b"")) != expected:
        message = "Spike original PLIC contexts differ from actual sorted M/S allocation"
        raise ValueError(message)
    return harts


def original_ram(tree: DeviceTree) -> tuple[Region, ...]:
    """Select exact original page-aligned RAM extents without simulator defaults or merging.

    Parameters
    ----------
    tree
        Complete original binary device-tree topology.

    Returns
    -------
    tuple of Region
        Enabled, disjoint physical RAM banks in ascending address order.

    Raises
    ------
    ValueError
        If RAM is absent, disabled, not page aligned or ambiguously overlapping.
    """
    regions: list[Region] = []
    for node in tree.nodes.values():
        if node.properties.get("device_type") != b"memory\0":
            continue
        if node.properties.get("status", b"okay\0") not in (b"okay\0", b"ok\0"):
            message = "Spike original RAM must be enabled"
            raise ValueError(message)
        regions.extend(register_regions(tree, node.path))
    if not regions:
        message = "Spike topology has no original RAM"
        raise ValueError(message)
    if any(region.address % PAGE_BYTES or region.size % PAGE_BYTES for region in regions):
        message = "Spike original RAM must be page aligned without simulator rounding"
        raise ValueError(message)
    regions.sort(key=lambda region: region.address)
    if any(left.address + left.size > right.address for left, right in pairwise(regions)):
        message = "Spike original RAM banks overlap"
        raise ValueError(message)
    return tuple(regions)


def spike_command(
    tools: SpikeTools,
    tree: DeviceTree,
    platform: AmpPlatform,
    *,
    plic_path: str,
    paths: SpikePaths,
) -> list[str]:
    """Emit exact actual CPU/PLIC/MMIO arguments with no instruction-count exit substitute.

    Parameters
    ----------
    tools
        Explicit simulator/plugin and functional clock bound.
    tree
        Original verified platform topology.
    platform
        Complete admitted original resources.
    plic_path
        Original selected simulator PLIC path.
    paths
        Prepared verified ISA image and exclusive event/tracking output directories.

    Returns
    -------
    list of str
        Actual Spike executable and closed argument vector, using coherent msu contexts.

    Raises
    ------
    ValueError
        If actual files, clock/time bounds, topology or plugin path delimiters are invalid.
    """
    if (
        not tools.executable.is_absolute()
        or not tools.executable.is_file()
        or not os.access(tools.executable, os.X_OK)
        or not tools.plugin.is_absolute()
        or not tools.plugin.is_file()
    ):
        message = "Spike simulator and plugin require explicit actual absolute files"
        raise ValueError(message)
    if (
        type(tools.rtc_nanoseconds) is not int
        or not 1 <= tools.rtc_nanoseconds <= MAX_RTC_NANOSECONDS
        or type(tools.time_limit) is not int
        or not MIN_TIME_LIMIT <= tools.time_limit <= UINT64_MAX
    ):
        message = "Spike functional clock and time limit are outside bounds"
        raise ValueError(message)
    image, output = paths.image, paths.output
    harts = original_harts(tree, plic_path)
    if platform.hart not in harts:
        message = "dedicated firmware hart is absent from actual Spike topology"
        raise ValueError(message)
    fields = [
        str(platform.device.aperture.address),
        str(platform.source),
        str(tools.rtc_nanoseconds),
        str(tools.time_limit),
        str(platform.memory.shared.address),
        str((image / "configuration.txt").resolve()),
        str((output / "events.bin").resolve()),
        str((output / "tracking_raw.csv").resolve()),
    ]
    if any("," in field or "\n" in field or "\r" in field for field in fields):
        message = "Spike plugin argument paths contain an unsupported delimiter"
        raise ValueError(message)
    return [
        str(tools.executable),
        f"-p{len(harts)}",
        "-m" + ",".join(f"{region.address}:{region.size}" for region in original_ram(tree)),
        "--hartids=" + ",".join(map(str, harts)),
        "--priv=msu",
        "--isa=RV64IMAC_Zicsr_Zifencei",
        "--pcs=" + ",".join(f"{hart}:{platform.memory.firmware.address}" for hart in harts),
        "--dtb=" + str((image / "platform.dtb").resolve()),
        "--extlib=" + str(tools.plugin),
        "--device=witness_axi," + ",".join(fields),
        str((image / "firmware.elf").resolve()),
    ]
