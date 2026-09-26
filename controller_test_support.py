# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native controller test builds

"""Build real native entry points for the shared controller fixtures."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def build_native_controllers(root: Path, directory: Path) -> tuple[Path, Path]:
    """Compile actual C and Rust public programs with strict C/UB checks.

    Parameters
    ----------
    root
        Witness checkout, also the Rust build-output owner.
    directory
        Managed C executable directory.

    Returns
    -------
    tuple of Path
        C and Rust streaming entry points.
    """
    binary = directory / "controller_cli"
    subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-Wstrict-prototypes",
            "-Wmissing-prototypes",
            "-fsanitize=undefined",
            "-fno-sanitize-recover=all",
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
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            "controllers/rust/Cargo.toml",
            "--release",
            "--locked",
            "--offline",
            "--target-dir",
            str(root / "controllers/rust/target"),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return binary, root / "controllers/rust/target/release/witness-controller"


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
