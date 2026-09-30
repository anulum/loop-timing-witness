# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP logger completion and captured stream agreement

"""Identify actual native compiler drivers and the subordinate programs they select."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from amp_rust_vectors import rust_vectors
from amp_tool_runtime import elf_interpreter, library_identities

from manifest_io import sha256_of_file


def executable_path(name: str) -> Path:
    """Resolve one actual executable by explicit path or the active build PATH.

    Parameters
    ----------
    name
        One compiler or tool program name, with no shell or wrapper argument string.

    Returns
    -------
    Path
        Resolved actual executable.

    Raises
    ------
    ValueError
        If the selected program is absent or not executable.
    """
    selected = shutil.which(name)
    if selected is None:
        message = "AMP build tool must be an actual executable: " + name
        raise ValueError(message)
    return Path(selected).resolve()


def compiler_identity(name: str, frontend: str) -> dict[str, Any]:
    """Retain actual driver version, assembler, linker and selected compiler frontend identities.

    Parameters
    ----------
    name
        Actual C or C++ compiler selected by the native Make recipe.
    frontend
        Selected native language frontend program, cc1 or cc1plus.

    Returns
    -------
    dict of str to Any
        Original driver and subordinate executable paths, hashes and version output.

    Raises
    ------
    OSError
        If actual selected programs are unavailable.
    ValueError
        If an advertised subordinate program cannot be resolved to an executable.
    subprocess.SubprocessError
        If the actual driver refuses introspection or exceeds the bounded timeout.
    """
    compiler = executable_path(name)
    driver = {"path": str(compiler), "sha256": sha256_of_file(compiler)}
    programs = {}
    for program in (frontend, "collect2", "as", "ld"):
        advertised = subprocess.check_output(
            [str(compiler), "-print-prog-name=" + program], text=True, timeout=10
        ).strip()
        path = Path(advertised)
        if not path.is_absolute():
            path = executable_path(advertised)
        if not path.is_file() or not os.access(path, os.X_OK):
            message = "AMP compiler selected unavailable executable: " + advertised
            raise ValueError(message)
        resolved = path.resolve()
        programs[program] = {"path": str(resolved), "sha256": sha256_of_file(resolved)}
    version = subprocess.check_output([str(compiler), "--version"], text=True, timeout=10)
    libraries = runtime_libraries([compiler, *(Path(item["path"]) for item in programs.values())])
    return {
        "driver": driver,
        "programs": programs,
        "version": version,
        "runtime_libraries": libraries,
    }


def rust_program_query(path: Path, query: str) -> str:
    """Run a fixed Rust introspection query while preserving a Rustup proxy's invocation name.

    Parameters
    ----------
    path
        Actual operator-selected executable, including an unresolved Rustup proxy pathname.
    query
        One of sysroot, version or target-libraries; arbitrary compiler arguments are refused.

    Returns
    -------
    str
        Complete bounded original compiler output. Transient Make jobserver descriptors are
        excluded from introspection because they are not executable identity inputs.

    Raises
    ------
    ValueError
        If the query or actual executable is unavailable.
    subprocess.SubprocessError
        If genuine compiler introspection fails or exceeds ten seconds.
    """
    options = {
        "sysroot": ["--print", "sysroot"],
        "version": ["-vV"],
        "target-libraries": [
            "--print",
            "target-libdir",
            "--target",
            "riscv64imac-unknown-none-elf",
        ],
    }
    if query not in options or not path.is_file() or not os.access(path, os.X_OK):
        message = "Rust introspection requires a fixed query and actual executable"
        raise ValueError(message)
    return subprocess.check_output(
        [str(path), *options[query]],
        text=True,
        timeout=10,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"MAKEFLAGS", "MFLAGS", "CARGO_MAKEFLAGS"}
        },
    )


def program_identity(name: str) -> dict[str, str]:
    """Freeze a selected actual build program and its bounded version output.

    Parameters
    ----------
    name
        Explicit program name or path used by the build.

    Returns
    -------
    dict of str to str
        Resolved executable path, original hash and actual version output, independent of
        transient Make jobserver descriptors.
    """
    path = executable_path(name)
    version = subprocess.check_output(
        [str(path), "--version"],
        stderr=subprocess.STDOUT,
        text=True,
        timeout=10,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"MAKEFLAGS", "MFLAGS", "CARGO_MAKEFLAGS"}
        },
    )
    return {"path": str(path), "sha256": sha256_of_file(path), "version": version}


def runtime_libraries(programs: list[Path]) -> dict[str, str]:
    """Freeze libraries actually selected by each trusted native build executable's loader.

    Parameters
    ----------
    programs
        Actual compiler, frontend, linker, generator and build helper selections.

    Returns
    -------
    dict of str to str
        Resolved interpreter and library file hashes under the original build environment.

    Raises
    ------
    ValueError
        If a native executable or loader record cannot be admitted.
    subprocess.SubprocessError
        If an actual loader fails or exceeds the bounded timeout.
    """
    identities: dict[str, str] = {}
    for program in sorted(set(programs)):
        interpreter = elf_interpreter(program)
        listing = subprocess.check_output(
            [str(interpreter), "--list", str(program)], text=True, timeout=10
        )
        identities.update(library_identities(interpreter, listing))
    return identities


def preprocess_image(directory: Path, commands: list[list[str]]) -> tuple[Path, ...]:
    """Run actual firmware compiler preprocessing with the original complete compile flag vectors.

    Parameters
    ----------
    directory
        Original new firmware image and actual compiler working directory.
    commands
        Exact trusted compile vectors generated by preparation, not receipt-supplied commands.

    Returns
    -------
    tuple of Path
        Original actual GCC preprocessing dependency records, before object compilation.
    """
    output = directory / "precompile"
    output.mkdir()
    records = []
    for index, command in enumerate(commands):
        record = output / f"input_{index}.d"
        argv = [
            *command[: command.index("-MD")],
            "-M",
            "-MT",
            f"objects/input_{index}.o",
            "-MF",
            str(record.relative_to(directory)),
            command[command.index("-c") + 1],
        ]
        with (output / f"input_{index}.log").open("xb") as log:
            subprocess.run(
                argv, cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30
            )
        records.append(record)
    return tuple(records)


def preprocess_rust(directory: Path, compiler: str) -> tuple[Path, ...]:
    """Type-check captured Rust sources with fixed compiler vectors before object compilation.

    Parameters
    ----------
    directory
        Exclusive prepared source directory containing the metadata output directory.
    compiler
        Original admitted absolute Rust compiler executable.

    Returns
    -------
    tuple of Path
        Actual metadata compiler dependency records for the safe core and C ABI adapter.

    Raises
    ------
    subprocess.SubprocessError
        If actual type checking refuses the original sources or exceeds the bounded timeout.
    OSError
        If exclusive diagnostic logs or original source inputs cannot be accessed.
    """
    for index, command in enumerate(rust_vectors(compiler, metadata=True)):
        with (directory / "rust_metadata" / f"input_{index}.log").open("xb") as log:
            subprocess.run(
                command,
                cwd=directory,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=60,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key not in {"MAKEFLAGS", "MFLAGS", "CARGO_MAKEFLAGS"}
                },
            )
    return tuple(directory / "rust_metadata" / name for name in ["core.d", "adapter.d"])


def simulator_identity(executable: Path, plugin: Path) -> dict[str, Any]:
    """Identify actual simulator version and its executable/plugin loader library selections.

    Parameters
    ----------
    executable
        Explicit actual admitted Spike executable.
    plugin
        Actual admitted native plugin library, never a receipt-supplied command.

    Returns
    -------
    dict of str to Any
        Original executable/version and actual native runtime library hashes.
    """
    selected = executable_path(str(executable))
    version = (
        subprocess.check_output(
            [str(selected), "--help"], stderr=subprocess.STDOUT, text=True, timeout=10
        )
        .strip()
        .partition("\n")[0]
    )
    interpreter = elf_interpreter(selected)
    libraries = runtime_libraries([selected])
    listing = subprocess.check_output(
        [str(interpreter), "--list", str(plugin)], text=True, timeout=10
    )
    libraries.update(library_identities(interpreter, listing))
    return {
        "path": str(selected),
        "sha256": sha256_of_file(selected),
        "version": version,
        "runtime_libraries": libraries,
    }


def spike_sdk_identity(source: Path, build: Path) -> dict[str, str]:
    """Record the actual SDK revision and complete tracked patch before generation.

    Parameters
    ----------
    source
        Explicit original matching Spike Git checkout.
    build
        Explicit original generated SDK header directory.

    Returns
    -------
    dict of str to str
        Original source/build paths, commit and tracked binary patch.
    """
    git = executable_path("git")
    revision = subprocess.check_output(
        [str(git), "-C", str(source), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    patch = subprocess.check_output(
        [str(git), "-C", str(source), "diff", "--binary", "HEAD"], text=True, timeout=10
    )
    return {
        "source": str(source.resolve()),
        "build": str(build.resolve()),
        "revision": revision,
        "patch": patch,
    }


def verilator_identity() -> dict[str, Any]:
    """Identify the actual wrapper, selected native backend and runtime root.

    Returns
    -------
    dict of str to Any
        Actual wrapper/backend hashes and versions plus the runtime include root.

    Raises
    ------
    ValueError
        If an ambient backend/root override would change the explicitly selected tool path.
    """
    if os.environ.get("VERILATOR_BIN") or os.environ.get("VERILATOR_ROOT"):
        message = "AMP Verilator backend/root environment overrides are not admitted"
        raise ValueError(message)
    wrapper = program_identity("verilator")
    root = subprocess.check_output(
        [wrapper["path"], "--getenv", "VERILATOR_ROOT"], text=True, timeout=10
    ).strip()
    backend = program_identity(str(Path(wrapper["path"]).parent / "verilator_bin"))
    return {**wrapper, "backend": backend, "root": str(Path(root).resolve())}
