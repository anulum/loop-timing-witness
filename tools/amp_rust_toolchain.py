# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original Rust compiler and RV64 target library custody

"""Resolve a Rust selector to actual compiler, Cargo and installed target-library bytes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from amp_build_toolchain import program_identity, runtime_libraries, rust_program_query

from manifest_io import sha256_of_file

TARGET = "riscv64imac-unknown-none-elf"


def _sysroot_programs(selected: Path) -> tuple[Path, Path, Path]:
    """Return the selected toolchain's sysroot and its compiler and Cargo programs.

    Parameters
    ----------
    selected
        Absolute selected compiler.

    Returns
    -------
    tuple[Path, Path, Path]
        Resolved sysroot, ``bin/rustc`` and ``bin/cargo``.

    Raises
    ------
    ValueError
        If either program is not an executable file.
    """
    sysroot = Path(rust_program_query(selected, "sysroot").strip()).resolve()
    compiler = sysroot / "bin/rustc"
    cargo = sysroot / "bin/cargo"
    for program in [compiler, cargo]:
        if not program.is_file() or not os.access(program, os.X_OK):
            message = "Rust sysroot must contain actual compiler and Cargo programs"
            raise ValueError(message)
    return sysroot, compiler, cargo


def _target_libraries(compiler: Path, sysroot: Path) -> list[Path]:
    """Return the RV64 target's archive and metadata pairs inside the sysroot.

    Parameters
    ----------
    compiler
        Sysroot compiler.
    sysroot
        Resolved sysroot.

    Returns
    -------
    list[Path]
        Sorted ``.rlib`` and ``.rmeta`` files.

    Raises
    ------
    ValueError
        If the target directory is outside the sysroot, core or compiler-builtins
        is missing, or archives and metadata are not regular file pairs.
    """
    target = Path(rust_program_query(compiler, "target-libraries").strip()).resolve()
    if target != (sysroot / "lib/rustlib" / TARGET / "lib").resolve() or not target.is_relative_to(
        sysroot
    ):
        message = "Rust target libraries must belong to the original compiler sysroot"
        raise ValueError(message)
    libraries = sorted((*target.glob("*.rlib"), *target.glob("*.rmeta")))
    archives = {p.stem for p in libraries if p.suffix == ".rlib"}
    metadata = {p.stem for p in libraries if p.suffix == ".rmeta"}
    if not any(name.startswith("libcore-") for name in archives) or not any(
        name.startswith("libcompiler_builtins-") for name in archives
    ):
        message = "Rust RV64 core and compiler-builtins target libraries are required"
        raise ValueError(message)
    if archives != metadata or any(not p.is_file() or p.is_symlink() for p in libraries):
        message = "Rust RV64 target archives and metadata must form regular file pairs"
        raise ValueError(message)
    return libraries


def rust_toolchain(selector: str) -> dict[str, Any]:
    """Freeze actual Rust build programs and complete installed RV64 target libraries.

    Parameters
    ----------
    selector
        Explicit rustc executable or Rustup proxy invocation, preserved before resolving symlinks.

    Returns
    -------
    dict of str to Any
        Actual compiler/Cargo paths, hashes, versions, target-library closure and loader libraries.
        Subsequent builds must invoke these actual paths rather than a mutable Rustup selection.

    Raises
    ------
    ValueError
        If selection, compiler identity or the installed target library closure is unavailable.
    OSError
        If original executable or library bytes cannot be read.
    subprocess.SubprocessError
        If the actual selector or compiler refuses bounded introspection.
    """
    invocation = shutil.which(selector)
    if invocation is None:
        message = "Rust compiler selector must be an actual executable"
        raise ValueError(message)
    selected = Path(invocation).absolute()
    sysroot, compiler, cargo = _sysroot_programs(selected)
    version = rust_program_query(selected, "version")
    actual_version = rust_program_query(compiler, "version")
    if version != actual_version:
        message = "Rust selector and original compiler identities disagree"
        raise ValueError(message)
    libraries = _target_libraries(compiler, sysroot)
    return {
        "compiler": program_identity(str(compiler)),
        "cargo": program_identity(str(cargo)),
        "verbose_version": actual_version,
        "target": TARGET,
        "target_libraries": {str(p): sha256_of_file(p) for p in libraries},
        "runtime_libraries": runtime_libraries([compiler, cargo]),
    }
