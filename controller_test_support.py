# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native controller test builds

"""Build real native entry points for the shared controller fixtures."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

C_COVERAGE_DIRECTORY = "WITNESS_C_COVERAGE_DIRECTORY"
"""Environment variable naming the directory of a GCC line and branch coverage build."""

RUST_COVERAGE_DIRECTORY = "WITNESS_RUST_COVERAGE_DIRECTORY"
"""Environment variable naming the directory of an LLVM line and branch coverage build of the
Rust controller; its ``target`` subdirectory holds the build."""

C_WARNINGS: tuple[str, ...] = (
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wconversion",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
)
"""The Makefile's ``CONTROLLER_WARNINGS``, every one an error."""
UNDEFINED_BEHAVIOUR_REFUSAL: tuple[str, ...] = ("-fsanitize=undefined", "-fno-sanitize-recover=all")
COVERAGE_INSTRUMENTATION: tuple[str, ...] = ("--coverage", "-fprofile-abs-path", "-O0")


def build_native_controllers(root: Path, directory: Path) -> tuple[Path, Path]:
    """Compile the actual C and Rust public streaming programs.

    Parameters
    ----------
    root
        Witness checkout, also the Rust build-output owner.
    directory
        Managed C executable directory, unless a C coverage directory is named.

    Returns
    -------
    tuple of Path
        C and Rust streaming entry points.
    """
    return build_c_controller(root, directory), build_rust_controller(root)


def build_c_controller(root: Path, directory: Path) -> Path:
    """Compile the C streaming program with strict warnings and undefined-behaviour refusal.

    When ``WITNESS_C_COVERAGE_DIRECTORY`` names a directory, the C program is
    built there with GCC line and branch counters at ``-O0`` instead, so the
    counters of every run collect beside its notes. That build omits the
    undefined-behaviour sanitizer: its boolean-load check adds a branch that
    only undefined behaviour can take, so complete branch coverage would be
    unreachable. Every ordinary build keeps the sanitizer.

    Parameters
    ----------
    root
        Witness checkout holding the C sources.
    directory
        Managed C executable directory, unless a coverage directory is named.

    Returns
    -------
    Path
        C streaming entry point.
    """
    coverage = os.environ.get(C_COVERAGE_DIRECTORY)
    if coverage:
        directory = Path(coverage)
        directory.mkdir(parents=True, exist_ok=True)
        checks = COVERAGE_INSTRUMENTATION
    else:
        checks = UNDEFINED_BEHAVIOUR_REFUSAL
    binary = directory / "controller_cli"
    subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-O2",
            *C_WARNINGS,
            *checks,
            "controllers/c/witness_controller.c",
            "controllers/c/controller_cli.c",
            "-o",
            str(binary),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return binary


def build_rust_controller(root: Path) -> Path:
    """Build the Rust streaming program, instrumented when a coverage directory is named.

    When ``WITNESS_RUST_COVERAGE_DIRECTORY`` names a directory, the program is built
    unoptimised in its ``target`` subdirectory with LLVM line and branch counters, the
    instrumentation of the native analysis coverage gate. Each run writes its profile to the
    caller's ``LLVM_PROFILE_FILE``. Otherwise the ordinary release build is used.

    Parameters
    ----------
    root
        Witness checkout, also the owner of the release build output.

    Returns
    -------
    Path
        Rust streaming entry point, selected from Cargo's JSON messages for a coverage build.

    Raises
    ------
    RuntimeError
        If Cargo reports no executable for the coverage build.
    """
    coverage = os.environ.get(RUST_COVERAGE_DIRECTORY)
    command = ["cargo", "build", "--manifest-path", "controllers/rust/Cargo.toml", "--locked"]
    if not coverage:
        target = root / "controllers/rust/target"
        command += ["--release", "--offline", "--target-dir", str(target)]
        subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
        return target / "release/witness-controller"
    environment = {
        **os.environ,
        "RUSTC_BOOTSTRAP": "1",
        "RUSTFLAGS": "-C instrument-coverage -Z coverage-options=branch",
    }
    command += ["--offline", "--target-dir", str(Path(coverage) / "target")]
    result = subprocess.run(
        [*command, "--bin", "witness-controller", "--message-format=json"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        message = json.loads(line)
        if message.get("reason") == "compiler-artifact" and message.get("executable"):
            return Path(message["executable"])
    message = "Cargo reported no Rust controller executable"
    raise RuntimeError(message)


@pytest.fixture(scope="session")
def native_controllers(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Build actual C/Rust CLI programs, with C undefined-behaviour refusal.

    Parameters
    ----------
    tmp_path_factory
        Managed native C executable storage.

    Returns
    -------
    tuple of Path
        C and Rust public streaming programs.
    """
    return build_native_controllers(
        Path(__file__).resolve().parent, tmp_path_factory.mktemp("controller-native")
    )
