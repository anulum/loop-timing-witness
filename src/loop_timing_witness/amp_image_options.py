# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — explicit original platform and firmware image CLI inputs

"""Share explicit platform admission arguments between source preparation and ELF verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .amp_memory import MemorySelection
from .device_tree_interrupts import PlicSelection

if TYPE_CHECKING:
    import argparse


@dataclass(frozen=True)
class ImageRequest:
    """Explicit resource selection shared by preparation and compiled image admission.

    Parameters
    ----------
    memory
        Original RAM/firmware/shared paths and actual stack/ABI requests.
    plic
        Original PLIC path, dedicated hart, retained source and concrete layout.
    device_path
        Original versioned Witness node.
    """

    memory: MemorySelection
    plic: PlicSelection
    device_path: str


def add_image_arguments(parser: argparse.ArgumentParser) -> None:
    """Register required original resource paths with no guessed board defaults.

    Parameters
    ----------
    parser
        Public preparation or verification parser.
    """
    parser.add_argument("--dtb", required=True, type=Path)
    parser.add_argument("--configuration", required=True, type=Path)
    parser.add_argument("--ram-node", required=True)
    parser.add_argument("--firmware-node", required=True)
    parser.add_argument("--telemetry-node", required=True)
    parser.add_argument("--device-node", required=True)
    parser.add_argument("--plic-node", required=True)
    parser.add_argument("--plic-layout", required=True, choices=["sifive", "spike"])
    parser.add_argument("--hart", required=True, type=int)
    parser.add_argument("--interrupt", required=True, type=int)
    parser.add_argument("--stack-bytes", required=True, type=int)


def image_request(args: argparse.Namespace) -> ImageRequest:
    """Construct the typed explicit request using original native ABI minimum and CLI choices.

    Parameters
    ----------
    args
        Namespace parsed with the complete required image arguments.

    Returns
    -------
    ImageRequest
        Explicit original resource request awaiting DTB admission.
    """
    return ImageRequest(
        MemorySelection(
            args.ram_node, args.firmware_node, args.telemetry_node, 16496, args.stack_bytes
        ),
        PlicSelection(args.plic_node, args.hart, args.interrupt, args.plic_layout),
        args.device_node,
    )


def verification_arguments(request: ImageRequest) -> list[str]:
    """Emit exact immutable resource arguments for verification within the prepared directory.

    Parameters
    ----------
    request
        Original complete resource selection.

    Returns
    -------
    list of str
        Original selected paths and scalar bounds, without shell quoting or inferred defaults.
    """
    return [
        "--dtb",
        "platform.dtb",
        "--configuration",
        "configuration.txt",
        "--ram-node",
        request.memory.ram_path,
        "--firmware-node",
        request.memory.firmware_path,
        "--telemetry-node",
        request.memory.shared_path,
        "--device-node",
        request.device_path,
        "--plic-node",
        request.plic.path,
        "--plic-layout",
        request.plic.binding,
        "--hart",
        str(request.plic.hart),
        "--interrupt",
        str(request.plic.source),
        "--stack-bytes",
        str(request.memory.stack_bytes),
    ]
