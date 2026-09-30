# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — portable original Rust archive and source receipt reconciliation

"""Verify complete captured Rust source and archive custody independently of live build tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from .amp_runtime_snapshot import validate_runtime_snapshot
from .amp_rust_dependencies import rust_dependency_hashes
from .amp_rust_vectors import ADAPTER, CORE, LIBRARY, TARGET, rust_vectors
from .manifest_io import load_json_object, sha256_of_file

HASHES = {
    "type": "object",
    "minProperties": 1,
    "propertyNames": {"pattern": "^/"},
    "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
}
PROGRAM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "sha256", "version"],
    "properties": {
        "path": {"type": "string", "pattern": "^/"},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "version": {"type": "string", "minLength": 1},
    },
}
TOOLCHAIN = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "compiler",
        "cargo",
        "verbose_version",
        "target",
        "target_libraries",
        "runtime_libraries",
    ],
    "properties": {
        "compiler": PROGRAM,
        "cargo": PROGRAM,
        "verbose_version": {"type": "string", "minLength": 1},
        "target": {"const": TARGET},
        "target_libraries": HASHES,
        "runtime_libraries": HASHES,
    },
}


def _admit_sources(directory: Path, data: dict[str, Any]) -> dict[str, str]:
    """Reconcile every captured original source and reject escaping snapshot paths.

    Parameters
    ----------
    directory
        Exclusive preparation directory.
    data
        Original decoded Rust preparation receipt.

    Returns
    -------
    dict of str to str
        Current original source hashes, matched to their captured identities.

    Raises
    ------
    ValueError
        If source identities or containment disagree.
    """
    names = [
        f"source/{component}/{name}"
        for component in [CORE, ADAPTER]
        for name in ["Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs"]
    ]
    root = directory.resolve()
    for name in names:
        if not (directory / name).resolve().is_relative_to(root / "source"):
            message = "Rust captured source paths escape original preparation"
            raise ValueError(message)
    sources = {name: sha256_of_file(directory / name) for name in names}
    if data.get("sources") != sources:
        message = "Rust captured original source bytes changed"
        raise ValueError(message)
    return sources


def _admit_target_libraries(directory: Path, data: dict[str, Any], live: dict[str, Any]) -> None:
    """Verify the complete captured original target-library index and every archive byte.

    Parameters
    ----------
    directory
        Exclusive preparation directory.
    data
        Original decoded Rust preparation receipt.
    live
        Admitted actual compiler identity and original target-library hashes.

    Raises
    ------
    ValueError
        If an index, contained archive path or original byte digest disagrees.
    """
    root = directory.resolve()
    names = live["target_libraries"]
    archives = {Path(name).stem for name in names if Path(name).suffix == ".rlib"}
    metadata = {Path(name).stem for name in names if Path(name).suffix == ".rmeta"}
    if (
        archives != metadata
        or not any(name.startswith("libcore-") for name in archives)
        or not any(name.startswith("libcompiler_builtins-") for name in archives)
        or any(Path(name).suffix not in {".rlib", ".rmeta"} for name in names)
    ):
        message = "Rust original target archives and metadata are incomplete"
        raise ValueError(message)
    index = {
        name: {"path": f"rust_target_libraries/{number:04d}{Path(name).suffix}", "sha256": digest}
        for number, (name, digest) in enumerate(sorted(names.items()))
    }
    if data.get("target_index") != index:
        message = "Rust original target library snapshot index disagrees"
        raise ValueError(message)
    for value in index.values():
        path = directory / value["path"]
        if not path.resolve().is_relative_to(root) or sha256_of_file(path) != value["sha256"]:
            message = "Rust captured target library bytes or paths changed"
            raise ValueError(message)


def validate_rust_preparation_snapshot(directory: Path, data: dict[str, Any]) -> None:
    """Admit captured original Rust inputs without accessing the former host compiler installation.

    Parameters
    ----------
    directory
        Captured original image and complete Rust input snapshots.
    data
        Original Rust preparation, already bound to captured outer image input hashes.

    Raises
    ------
    ValueError
        If captured schema, compiler identity, vectors, sources, libraries or metadata disagree.
    OSError
        If original captured inputs are absent.
    """
    identity = data.get("toolchain")
    if data.get("schema") != "loop-timing-witness.rust-preparation.v1" or not Draft202012Validator(
        TOOLCHAIN
    ).is_valid(identity):
        message = "Rust captured preparation or original toolchain identity is invalid"
        raise ValueError(message)
    live = cast("dict[str, Any]", identity)
    compiler = live["compiler"]["path"]
    for field, metadata in [("metadata_commands", True), ("compile_commands", False)]:
        if data.get(field) != rust_vectors(compiler, metadata=metadata):
            message = "Rust captured original compiler vectors disagree"
            raise ValueError(message)
    validate_runtime_snapshot(directory / "rust_runtime", live["runtime_libraries"])
    sources = _admit_sources(directory, data)
    _admit_target_libraries(directory, data, live)
    records = tuple(directory / "rust_metadata" / name for name in ["core.d", "adapter.d"])
    hashes = {str(path.relative_to(directory)): sha256_of_file(path) for path in records}
    if data.get("dependency_records") != hashes:
        message = "Rust captured original metadata records changed"
        raise ValueError(message)
    actual = rust_dependency_hashes(records, directory)
    expected = {name: sources[name] for name in sources if name.endswith("/src/lib.rs")}
    if data.get("dependencies") != actual or actual != expected:
        message = "Rust captured original metadata source closure changed"
        raise ValueError(message)


def validate_rust_image_receipt(
    directory: Path, image: dict[str, Any], preparation: dict[str, Any]
) -> None:
    """Reconcile captured Rust preparation, compiled source records and actual archive outputs.

    Parameters
    ----------
    directory
        Captured original image directory with actual compiled Rust artifacts.
    image
        Original image receipt bound to captured image.json bytes.
    preparation
        Original platform preparation bound to captured preparation.json bytes.

    Raises
    ------
    ValueError
        If original backend, nested receipt or actual compiled byte identities disagree.
    OSError
        If captured compiler output or original preparation files are absent.
    """
    if "kernel_backend" not in preparation:
        if "kernel_backend" in image or "rust_kernel" in image:
            message = "Rust receipt contradicts the original C arithmetic selection"
            raise ValueError(message)
        return
    if preparation["kernel_backend"] != "rust" or image.get("kernel_backend") != "rust":
        message = "Rust original arithmetic backend declarations disagree"
        raise ValueError(message)
    data = load_json_object(directory / "rust_preparation.json")
    validate_rust_preparation_snapshot(directory, data)
    records = tuple(directory / "objects/rust" / name for name in ["core.d", "adapter.d"])
    if rust_dependency_hashes(records, directory) != data["dependencies"]:
        message = "Rust captured final source closure differs from original metadata"
        raise ValueError(message)
    library = directory / LIBRARY
    if not library.read_bytes().startswith(b"!<arch>\n"):
        message = "Rust captured compiler output is not a static archive"
        raise ValueError(message)
    paths = [*records, library, directory / "objects/rust/libwitness_controller.rlib"]
    expected = {
        "preparation": data,
        "outputs": {str(path.relative_to(directory)): sha256_of_file(path) for path in paths},
    }
    if image.get("rust_kernel") != expected:
        message = "Rust original archive receipt or actual compiler output bytes changed"
        raise ValueError(message)
