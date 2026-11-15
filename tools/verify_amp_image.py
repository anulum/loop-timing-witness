# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public original firmware image and prepared-input drift verification

"""Verify original firmware contracts and retain a source-bound image manifest."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from amp_exit_channel import admit_exit_channel
from amp_image_contract import admit_image_contract
from amp_image_dependencies import image_dependency_hashes
from amp_image_options import ImageRequest, add_image_arguments, image_request
from amp_platform import bind_platform
from amp_prepared_inputs import PreparedInputs, admit_preparation
from amp_run_input import read_amp_run
from amp_rust_admission import admit_rust_archive
from device_tree_blob import decode_device_tree

from manifest_io import canonical_json_bytes, sha256_of_file

if TYPE_CHECKING:
    from amp_contract import AmpRun
    from amp_elf import LoadSegment
    from amp_platform import AmpPlatform

DEPENDENCY_RECORD_COUNT = 5


def _dependencies(directory: Path, *, rust: bool) -> dict[str, str]:
    """Digest every real compiler-recorded source/system dependency after image admission.

    Parameters
    ----------
    directory
        Prepared image and actual compiler dependency files.
    rust
        Explicit admitted Rust selection, with four platform C/assembly translation units.

    Returns
    -------
    dict of str to str
        Actual dependency file paths and byte hashes.

    Raises
    ------
    ValueError
        If original compiler dependency records are absent or malformed.
    """
    records = sorted((directory / "objects").glob("*.o.d"))
    count = DEPENDENCY_RECORD_COUNT - int(rust)
    if len(records) != count:
        message = (
            "AMP requires all four platform compiler dependency records"
            if rust
            else "AMP requires all five actual compiler dependency records"
        )
        raise ValueError(message)
    return image_dependency_hashes(tuple(records), directory)


def _admit_firmware(
    directory: Path,
    dtb: Path,
    configuration: Path,
    request: ImageRequest,
    prepared: PreparedInputs,
) -> tuple[AmpPlatform, AmpRun, tuple[LoadSegment, ...]]:
    """Bind the topology and admit the firmware's contract and exit channel.

    Parameters
    ----------
    directory
        Image build directory holding ``firmware.elf``.
    dtb, configuration
        Verified topology and run configuration.
    request
        Explicit original resource and stack selection.
    prepared
        Admitted preparation with the target mode.

    Returns
    -------
    tuple[AmpPlatform, AmpRun, tuple[LoadSegment, ...]]
        Bound platform, decoded run and admitted load segments.
    """
    platform = bind_platform(
        decode_device_tree(dtb.read_bytes()), request.memory, request.device_path, request.plic
    )
    run = read_amp_run(configuration.read_bytes())
    image = directory / "firmware.elf"
    segments = admit_image_contract(image.read_bytes(), platform, run, request.memory.stack_bytes)
    admit_exit_channel(image.read_bytes(), segments, isa=prepared.isa)
    return platform, run, segments


def _check_inputs(hashes: dict[str, str], dtb: Path, configuration: Path) -> None:
    """Require the verification inputs to be the prepared topology and configuration.

    Parameters
    ----------
    hashes
        Prepared input digests.
    dtb, configuration
        Verification inputs.

    Raises
    ------
    ValueError
        If either digest differs.
    """
    if (
        sha256_of_file(dtb) != hashes["platform.dtb"]
        or sha256_of_file(configuration) != hashes["configuration.txt"]
    ):
        message = "AMP verification inputs differ from the original preparation"
        raise ValueError(message)


def _mode_fields(directory: Path, prepared: PreparedInputs) -> dict[str, object]:
    """Return the manifest's schema, kernel and execution-mode fields.

    Parameters
    ----------
    directory
        Image build directory, holding the Rust archive when built.
    prepared
        Admitted preparation.

    Returns
    -------
    dict[str, object]
        Schema, the admitted Rust kernel when built, simulation-only and
        physical-verification flags and the exit mode.
    """
    return {
        "schema": "loop-timing-witness.amp-image.v1",
        **(
            {"kernel_backend": "rust", "rust_kernel": admit_rust_archive(directory)}
            if prepared.rust is not None
            else {}
        ),
        "simulation_only": True,
        "physical_verified": False,
        "exit_mode": "isa_htif" if prepared.isa else "parked",
    }


def _digests(directory: Path, dtb: Path, configuration: Path) -> dict[str, str]:
    """Return the digests of the firmware, topology, configuration and preparation.

    Parameters
    ----------
    directory
        Image build directory.
    dtb, configuration
        Verified topology and run configuration.

    Returns
    -------
    dict[str, str]
        The four manifest digest fields.
    """
    return {
        "firmware_sha256": sha256_of_file(directory / "firmware.elf"),
        "dtb_sha256": sha256_of_file(dtb),
        "configuration_sha256": sha256_of_file(configuration),
        "preparation_sha256": sha256_of_file(directory / "preparation.json"),
    }


def _write_manifest(manifest: Path, encoded: bytes) -> None:
    """Write the image manifest, or accept an existing one with identical bytes.

    Parameters
    ----------
    manifest
        ``image.json`` path.
    encoded
        Canonical manifest bytes.

    Raises
    ------
    ValueError
        If a manifest with other bytes already exists.
    """
    if manifest.exists():
        if manifest.read_bytes() != encoded:
            message = "AMP verified image manifest already exists with different bytes"
            raise ValueError(message)
    else:
        with manifest.open("xb") as output:
            output.write(encoded)


def verify_image(directory: Path, dtb: Path, configuration: Path, request: ImageRequest) -> Path:
    """Admit actual original ELF bytes and write the immutable successful image manifest.

    Parameters
    ----------
    directory
        Prepared directory with actual linked firmware and build logs.
    dtb
        Retained original platform binary.
    configuration
        Retained complete original native run configuration.
    request
        Explicit original resource and integer stack selection.

    Returns
    -------
    Path
        Successful source-bound image manifest, absent after failed verification.

    Raises
    ------
    OSError
        If an original input, compiler dependency or output is unavailable.
    ValueError
        If preparation drift, topology or compiled firmware contradicts admission.
    """
    prepared = admit_preparation(directory)
    _check_inputs(prepared.hashes, dtb, configuration)
    platform, run, segments = _admit_firmware(directory, dtb, configuration, request, prepared)
    dependencies = _dependencies(directory, rust=prepared.rust is not None)
    if dependencies != prepared.dependencies:
        message = "AMP compiled firmware dependencies differ from original preprocessing"
        raise ValueError(message)
    encoded = canonical_json_bytes(
        {
            **_mode_fields(directory, prepared),
            **_digests(directory, dtb, configuration),
            "platform": asdict(platform),
            "run": asdict(run),
            "stack_bytes": request.memory.stack_bytes,
            "segments": [asdict(segment) for segment in segments],
            "inputs": prepared.hashes,
            "compiler_dependencies": dependencies,
            "toolchain": prepared.toolchain,
        }
    )
    manifest = directory / "image.json"
    _write_manifest(manifest, encoded)
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Verify original prepared firmware through the public command line.

    Parameters
    ----------
    argv
        Explicit CLI arguments or process arguments.

    Returns
    -------
    int
        Zero after actual source/image admission, one after a retained refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    add_image_arguments(parser)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = verify_image(args.directory, args.dtb, args.configuration, image_request(args))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP image verification: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"AMP image verification: PASS: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
