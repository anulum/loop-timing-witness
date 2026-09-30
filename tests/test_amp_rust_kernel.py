# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real C ABI consumption of the freestanding Rust kernel

"""Compile the actual Rust adapter and compare its public C entry points with the C kernel."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "runtime/bare_metal/rust_kernel/Cargo.toml"
WARNINGS = [
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wconversion",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
]


def run_command(command: list[str], directory: Path, name: str) -> None:
    """Run one actual compiler or executable and retain its complete diagnostics.

    Parameters
    ----------
    command
        Literal compiler or public executable vector.
    directory
        Exclusive test output directory.
    name
        Diagnostic file stem.
    """
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False, timeout=90)
    (directory / (name + ".log")).write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors="replace")


@pytest.fixture(scope="module")
def rust_kernel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the genuine host and RV64 adapter archives with strict Rust checks.

    Parameters
    ----------
    tmp_path_factory
        Exclusive native build allocation.

    Returns
    -------
    Path
        Actual native output directory including the Rust library and linked public CLIs.
    """
    directory = tmp_path_factory.mktemp("rust-amp-kernel")
    target = directory / "target"
    common = [
        "--offline",
        "--locked",
        "--manifest-path",
        str(MANIFEST),
        "--target-dir",
        str(target),
    ]
    run_command(["cargo", "fmt", "--manifest-path", str(MANIFEST), "--check"], directory, "format")
    run_command(
        [
            "cargo",
            "clippy",
            *common,
            "--target",
            "riscv64imac-unknown-none-elf",
            "--",
            "-D",
            "warnings",
        ],
        directory,
        "clippy-rv64",
    )
    run_command(["cargo", "clippy", *common, "--", "-D", "warnings"], directory, "clippy-host")
    run_command(["cargo", "build", "--release", *common], directory, "build-host")
    run_command(
        ["cargo", "build", "--release", *common, "--target", "riscv64imac-unknown-none-elf"],
        directory,
        "build-rv64",
    )
    archive = target / "release/libwitness_amp_rust_kernel.a"
    gcc = ["gcc", "-std=gnu11", "-O2", *WARNINGS, "-Icontrollers/c"]
    panic = str(ROOT / "tests/native/amp_rust_host_panic.c")
    run_command(
        [
            *gcc,
            "tests/native/controller_api_test.c",
            panic,
            str(archive),
            "-Wl,--gc-sections",
            "-o",
            str(directory / "api"),
        ],
        directory,
        "link-api",
    )
    run_command(
        [
            *gcc,
            "controllers/c/controller_cli.c",
            panic,
            str(archive),
            "-Wl,--gc-sections",
            "-o",
            str(directory / "rust-cli"),
        ],
        directory,
        "link-rust-cli",
    )
    run_command(
        [
            *gcc,
            "controllers/c/controller_cli.c",
            "controllers/c/witness_controller.c",
            "-o",
            str(directory / "c-cli"),
        ],
        directory,
        "link-c-cli",
    )
    return directory


def test_original_c_api_accepts_rust_kernel(rust_kernel: Path) -> None:
    """Exercise uninitialised output storage, every coefficient refusal, reset and recovery.

    Parameters
    ----------
    rust_kernel
        Compiled actual Rust C ABI and original C API assertion program.
    """
    run_command([str(rust_kernel / "api")], rust_kernel, "api-result")


@pytest.mark.parametrize("mode", ["pid", "lqr"])
def test_c_stream_calls_rust_kernel(rust_kernel: Path, mode: str) -> None:
    """Match native C output over extremes, negative fractions and a real reset boundary.

    Parameters
    ----------
    rust_kernel
        Independently linked public C protocol clients for the C and Rust implementations.
    mode
        Original PID or LQR entry selection.
    """
    coefficients = (
        "2147483647,2147483647,16777216,2147483647,-2147483648,2147483647,"
        "-2147483648,-2147483648,2147483647,-2147483648,2147483647"
    )
    rows = [
        "0,2147483647,-2147483648,2147483647",
        "1,-2147483648,2147483647,-2147483648",
        "2,0,-1,-1",
        "3,0,1,1",
        "reset",
        "0,16777216,0,0",
        "1,0,0,0",
    ]
    payload = (coefficients + "\n" + "\n".join(rows) + "\n").encode()
    observed = []
    for implementation in ["c", "rust"]:
        result = subprocess.run(
            [str(rust_kernel / (implementation + "-cli")), mode],
            input=payload,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert not result.stderr
        observed.append(result.stdout)
    assert observed[0] == observed[1]
    assert len(observed[0].splitlines()) == len(rows) - 1
