# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original Rust source snapshots and compiler build vectors

"""Prepare Rust arithmetic and C ABI sources with explicit original compiler inputs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from amp_build_toolchain import preprocess_rust
from amp_runtime_snapshot import snapshot_runtime
from amp_rust_dependencies import rust_dependency_hashes
from amp_rust_toolchain import rust_toolchain
from amp_rust_vectors import ADAPTER, CORE, rust_vectors

from manifest_io import canonical_json_bytes, sha256_of_file


def _snapshot_sources(root: Path, directory: Path) -> dict[str, str]:
    """Copy the Rust core and adapter sources exclusively and return their digests.

    Parameters
    ----------
    root
        Source checkout.
    directory
        Image build directory receiving ``source``.

    Returns
    -------
    dict[str, str]
        Digest of every copied source by its ``source/`` path.

    Raises
    ------
    ValueError
        If a source is not a contained regular file or changes while copied.
    """
    names = [
        f"{component}/{name}"
        for component in [CORE, ADAPTER]
        for name in ["Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs"]
    ]
    hashes = {}
    source_root = root.resolve()
    for name in names:
        source = root / name
        if (
            not source.is_file()
            or source.is_symlink()
            or not source.resolve().is_relative_to(source_root)
        ):
            message = "Rust original source must be a contained regular file"
            raise ValueError(message)
        digest = sha256_of_file(source)
        target = directory / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
        if sha256_of_file(target) != digest:
            message = "Rust original source changed during snapshot"
            raise ValueError(message)
        hashes["source/" + name] = digest
    return hashes


def _snapshot_rust_runtime(directory: Path, runtime_libraries: dict[str, str]) -> None:
    """Snapshot the Rust toolchain's runtime libraries into ``rust_runtime``.

    Parameters
    ----------
    directory
        Image build directory.
    runtime_libraries
        Digest of every runtime library by its original path.
    """
    runtime = directory / "rust_runtime"
    runtime.mkdir()
    snapshot_runtime(runtime, runtime_libraries)


def _snapshot_target_libraries(
    directory: Path, target_libraries: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Copy each Rust target library under a numbered name and index it.

    Parameters
    ----------
    directory
        Image build directory receiving ``rust_target_libraries``.
    target_libraries
        Digest of every target library by its original path.

    Returns
    -------
    dict[str, dict[str, str]]
        Copied path and digest of every library by its original path.

    Raises
    ------
    ValueError
        If a library changes while copied.
    """
    libraries = directory / "rust_target_libraries"
    libraries.mkdir()
    index = {}
    for number, (name, digest) in enumerate(sorted(target_libraries.items())):
        target = libraries / f"{number:04d}{Path(name).suffix}"
        shutil.copyfile(name, target)
        if sha256_of_file(target) != digest:
            message = "Rust original target library changed during snapshot"
            raise ValueError(message)
        index[name] = {"path": str(target.relative_to(directory)), "sha256": digest}
    return index


def prepare_rust_sources(root: Path, directory: Path, selector: str) -> dict[str, Any]:
    """Capture original Rust sources, installed target archives, runtime files and compile vectors.

    Parameters
    ----------
    root
        Canonical source checkout.
    directory
        Exclusive admitted firmware preparation directory.
    selector
        Operator-selected original Rust compiler or Rustup invocation.

    Returns
    -------
    dict of str to Any
        Source hashes, actual complete toolchain and exact precompile/final compile vectors.

    Raises
    ------
    OSError
        If original input bytes or exclusive source directories cannot be accessed.
    ValueError
        If original compiler, target libraries or source bytes drift during capture.
    """
    identity = rust_toolchain(selector)
    hashes = _snapshot_sources(root, directory)
    _snapshot_rust_runtime(directory, identity["runtime_libraries"])
    index = _snapshot_target_libraries(directory, identity["target_libraries"])
    (directory / "objects/rust").mkdir(parents=True)
    (directory / "rust_metadata").mkdir()
    records = preprocess_rust(directory, identity["compiler"]["path"])
    dependencies = rust_dependency_hashes(records, directory)
    if rust_toolchain(identity["compiler"]["path"]) != identity:
        message = "Rust original toolchain changed during metadata compilation"
        raise ValueError(message)
    record = {
        "schema": "loop-timing-witness.rust-preparation.v1",
        "toolchain": identity,
        "sources": hashes,
        "target_index": index,
        "metadata_commands": rust_vectors(identity["compiler"]["path"], metadata=True),
        "compile_commands": rust_vectors(identity["compiler"]["path"], metadata=False),
        "dependencies": dependencies,
        "dependency_records": {
            str(path.relative_to(directory)): sha256_of_file(path) for path in records
        },
    }
    with (directory / "rust_preparation.json").open("xb") as stream:
        stream.write(canonical_json_bytes(record))
    return record
