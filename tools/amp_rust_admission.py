# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original Rust preparation admission before and after compilation

"""Reconcile original Rust preparation against actual source, toolchain and archive bytes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amp_rust_dependencies import rust_dependency_hashes
from amp_rust_toolchain import rust_toolchain
from amp_rust_vectors import LIBRARY

from loop_timing_witness.amp_rust_receipt import validate_rust_preparation_snapshot
from manifest_io import parse_json_object, sha256_of_file

if TYPE_CHECKING:
    from pathlib import Path


def admit_rust_preparation(directory: Path) -> dict[str, Any]:
    """Refuse changed original Rust compiler, sources, target libraries and metadata records.

    Parameters
    ----------
    directory
        Original prepared image directory, containing its captured Rust inputs.

    Returns
    -------
    dict of str to Any
        Original preparation after complete live and captured byte reconciliation.

    Raises
    ------
    ValueError
        If original preparation identities or paths disagree with actual input bytes.
    OSError
        If required original compiler, source, library or dependency bytes are absent.
    """
    data = parse_json_object((directory / "rust_preparation.json").read_bytes(), "Rust preparation")
    identity = data.get("toolchain")
    if data.get("schema") != "loop-timing-witness.rust-preparation.v1" or not isinstance(
        identity, dict
    ):
        message = "Rust preparation schema or original toolchain identity is invalid"
        raise ValueError(message)
    compiler = identity.get("compiler")
    if not isinstance(compiler, dict) or not isinstance(compiler.get("path"), str):
        message = "Rust preparation lacks its original compiler path"
        raise ValueError(message)
    live = rust_toolchain(compiler["path"])
    if live != identity:
        message = "Rust original compiler, target or runtime libraries changed"
        raise ValueError(message)
    validate_rust_preparation_snapshot(directory, data)
    return data


def admit_rust_archive(directory: Path) -> dict[str, Any]:
    """Match actual final compilation dependencies to original metadata and hash output bytes.

    Parameters
    ----------
    directory
        Original prepared image after genuine safe-core and ABI-adapter compilation.

    Returns
    -------
    dict of str to Any
        Verified original preparation and actual library and compiler-record byte hashes.

    Raises
    ------
    ValueError
        If compiled dependency closure or archive framing contradicts original preparation.
    OSError
        If actual original preparation or final compiler outputs are absent.
    """
    prepared = admit_rust_preparation(directory)
    records = tuple(directory / "objects/rust" / name for name in ["core.d", "adapter.d"])
    if rust_dependency_hashes(records, directory) != prepared["dependencies"]:
        message = "Rust final compiler source dependencies differ from original metadata"
        raise ValueError(message)
    library = directory / LIBRARY
    if not library.read_bytes().startswith(b"!<arch>\n"):
        message = "Rust actual static library must be a compiler-produced archive"
        raise ValueError(message)
    paths = [*records, library, directory / "objects/rust/libwitness_controller.rlib"]
    return {
        "preparation": prepared,
        "outputs": {str(path.relative_to(directory)): sha256_of_file(path) for path in paths},
    }
