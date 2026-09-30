# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — offline original firmware contract reconciliation

"""Reconcile captured image declarations with original topology and actual executable bytes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .amp_exit_channel import admit_exit_channel
from .amp_image_contract import admit_image_contract
from .amp_image_options import ImageRequest, verification_arguments
from .amp_memory import MemorySelection
from .amp_platform import bind_platform
from .amp_run_input import read_amp_run
from .amp_rust_receipt import validate_rust_image_receipt
from .device_tree_blob import decode_device_tree
from .device_tree_interrupts import PlicSelection
from .manifest_io import load_json_object

OPTIONS = (
    "--dtb",
    "--configuration",
    "--ram-node",
    "--firmware-node",
    "--telemetry-node",
    "--device-node",
    "--plic-node",
    "--plic-layout",
    "--hart",
    "--interrupt",
    "--stack-bytes",
)
PREFIX_SIZE = 4
MAILBOX_BYTES = 16496


def recorded_request(directory: Path) -> ImageRequest:
    """Decode the original verification selection without executing its recorded command.

    Parameters
    ----------
    directory
        Captured image directory containing original build_commands.json.

    Returns
    -------
    ImageRequest
        Explicit original resource selection, still subject to binary topology admission.

    Raises
    ------
    ValueError
        If the recorded vector has missing, duplicated or noncanonical resource arguments.
    """
    vector = load_json_object(directory / "build_commands.json").get("verify")
    if (
        not isinstance(vector, list)
        or len(vector) != PREFIX_SIZE + 2 * len(OPTIONS)
        or any(not isinstance(value, str) for value in vector)
        or not Path(vector[0]).is_absolute()
        or vector[1:PREFIX_SIZE] != ["source/tools/verify_amp_image.py", "--directory", "."]
        or tuple(vector[PREFIX_SIZE::2]) != OPTIONS
    ):
        message = "AMP original image verification vector is invalid"
        raise ValueError(message)
    arguments = dict(zip(vector[PREFIX_SIZE::2], vector[PREFIX_SIZE + 1 :: 2], strict=True))
    request = ImageRequest(
        MemorySelection(
            arguments["--ram-node"],
            arguments["--firmware-node"],
            arguments["--telemetry-node"],
            MAILBOX_BYTES,
            int(arguments["--stack-bytes"]),
        ),
        PlicSelection(
            arguments["--plic-node"],
            int(arguments["--hart"]),
            int(arguments["--interrupt"]),
            arguments["--plic-layout"],
        ),
        arguments["--device-node"],
    )
    if vector[PREFIX_SIZE:] != verification_arguments(request):
        message = "AMP original image verification arguments disagree"
        raise ValueError(message)
    return request


def validate_image_receipt(
    directory: Path, image: dict[str, Any], preparation: dict[str, Any]
) -> None:
    """Re-admit actual captured firmware and reconcile all duplicated image contract declarations.

    Parameters
    ----------
    directory
        Captured original firmware, topology, configuration and build vectors.
    image
        Original verified image metadata with its outer byte hashes already admitted.
    preparation
        Original preparation with complete compiler and captured input identities admitted.

    Raises
    ------
    ValueError
        If source identities, simulation mode, original resource selection or ELF contract disagree.
    """
    toolchain = preparation["toolchain"]
    if (
        preparation.get("schema") != "loop-timing-witness.amp-image-preparation.v1"
        or preparation.get("isa") is not True
        or preparation.get("compiler") != toolchain["driver"]["path"]
        or preparation.get("compiler_sha256") != toolchain["driver"]["sha256"]
        or "compiler" in preparation["inputs"]
        or image.get("inputs")
        != {"compiler": preparation.get("compiler_sha256"), **preparation["inputs"]}
        or image.get("schema") != "loop-timing-witness.amp-image.v1"
        or image.get("simulation_only") is not True
        or image.get("physical_verified") is not False
        or image.get("exit_mode") != "isa_htif"
    ):
        message = "AMP original image preparation or mode declarations disagree"
        raise ValueError(message)
    validate_rust_image_receipt(directory, image, preparation)
    request = recorded_request(directory)
    platform = bind_platform(
        decode_device_tree((directory / "platform.dtb").read_bytes()),
        request.memory,
        request.device_path,
        request.plic,
    )
    run = read_amp_run((directory / "configuration.txt").read_bytes())
    content = (directory / "firmware.elf").read_bytes()
    segments = admit_image_contract(content, platform, run, request.memory.stack_bytes)
    admit_exit_channel(content, segments, isa=True)
    if (
        image.get("platform") != asdict(platform)
        or image.get("run") != {**asdict(run), "coefficients": list(run.coefficients)}
        or image.get("stack_bytes") != request.memory.stack_bytes
        or image.get("segments") != [asdict(segment) for segment in segments]
    ):
        message = "AMP original image declarations differ from captured topology or firmware"
        raise ValueError(message)
