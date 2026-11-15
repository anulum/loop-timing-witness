# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original firmware preparation and pre-compilation input admission

"""Admit original firmware preparation independently of any already compiled output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amp_build_toolchain import compiler_identity
from amp_image_dependencies import verify_precompile_dependencies
from amp_runtime_snapshot import validate_runtime_snapshot
from amp_rust_admission import admit_rust_preparation

from manifest_io import parse_json_object, sha256_of_file

SCHEMA = "loop-timing-witness.amp-image-preparation.v1"


@dataclass(frozen=True)
class PreparedInputs:
    """Verified original source identities and explicitly selected target exit mode.

    Parameters
    ----------
    hashes
        Verified original source and compiler digests.
    isa
        Original preparation's explicit ISA HTIF mode.
    compiler
        Actual admitted original compiler executable.
    toolchain
        Original driver and subordinate identities matched against the live installed toolchain.
    dependencies
        Original complete preprocessing source/header identities.
    rust
        Admitted original Rust source/toolchain preparation when explicitly selected.
    """

    hashes: dict[str, str]
    isa: bool
    compiler: Path
    toolchain: dict[str, Any]
    dependencies: dict[str, str]
    rust: dict[str, Any] | None = None


def _checked_identity(data: dict[str, Any]) -> tuple[str, str, dict[Any, Any]]:
    """Return the prepared compiler, its digest and the inputs, checking the compiler bytes.

    Parameters
    ----------
    data
        Decoded preparation.

    Returns
    -------
    tuple[str, str, dict[Any, Any]]
        Absolute compiler path, its digest and the non-empty input digests.

    Raises
    ------
    ValueError
        If a field has the wrong type, the inputs are empty, or the compiler is
        not absolute or its bytes changed.
    """
    compiler, digest, inputs = data.get("compiler"), data.get("compiler_sha256"), data.get("inputs")
    if (
        not isinstance(compiler, str)
        or not isinstance(digest, str)
        or not isinstance(inputs, dict)
        or not inputs
    ):
        message = "AMP preparation compiler/input identity is invalid"
        raise ValueError(message)
    if not Path(compiler).is_absolute() or sha256_of_file(Path(compiler)) != digest:
        message = "AMP prepared compiler bytes changed"
        raise ValueError(message)
    return compiler, digest, inputs


def _checked_inputs(directory: Path, inputs: dict[Any, Any]) -> dict[str, str]:
    """Require the essential inputs and verify every input's path and bytes.

    Parameters
    ----------
    directory
        Image build directory.
    inputs
        Recorded input digests by relative name.

    Returns
    -------
    dict[str, str]
        The verified input digests, in recorded order.

    Raises
    ------
    ValueError
        If an essential input is missing, or a name or digest is not text, a path
        leaves the directory or its bytes changed.
    """
    required = {
        "platform.dtb",
        "configuration.txt",
        "Makefile",
        "contract.c",
        "source/tools/verify_amp_image.py",
    }
    if not required.issubset(inputs):
        message = "AMP preparation lacks required original input identities"
        raise ValueError(message)
    result = {}
    root = directory.resolve()
    for name, expected in inputs.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            message = "AMP preparation input names and hashes must be strings"
            raise ValueError(message)
        path = directory / name
        if (
            Path(name).is_absolute()
            or not path.resolve().is_relative_to(root)
            or sha256_of_file(path) != expected
        ):
            message = "AMP prepared source/input bytes or paths changed"
            raise ValueError(message)
        result[name] = expected
    return result


def admit_preparation(directory: Path) -> PreparedInputs:
    """Require original preparation identity and refuse source or compiler byte drift.

    Parameters
    ----------
    directory
        Original exclusive prepared image directory.

    Returns
    -------
    PreparedInputs
        Original verified input hashes and explicit exit mode.

    Raises
    ------
    ValueError
        If original preparation shape, paths, source or executable hashes differ.
    """
    data = parse_json_object((directory / "preparation.json").read_bytes(), "AMP preparation")
    if data.get("schema") != SCHEMA or type(data.get("isa")) is not bool:
        message = "AMP preparation schema or mode is invalid"
        raise ValueError(message)
    compiler, digest, inputs = _checked_identity(data)
    toolchain = compiler_identity(compiler, "cc1")
    if data.get("toolchain") != toolchain:
        message = "AMP prepared compiler subprograms or version changed"
        raise ValueError(message)
    validate_runtime_snapshot(directory, toolchain["runtime_libraries"])
    result = {"compiler": digest, **_checked_inputs(directory, inputs)}
    dependencies = verify_precompile_dependencies(directory, data)
    rust = admit_rust_preparation(directory) if "kernel_backend" in data else None
    return PreparedInputs(result, data["isa"], Path(compiler), toolchain, dependencies, rust)
