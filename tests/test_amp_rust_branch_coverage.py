# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — measured Rust safe-core and C ABI statement/branch coverage

"""Profile original Rust code through C clients, core tests and a genuine host panic."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUST_FLAGS = "-C instrument-coverage -Z coverage-options=branch"
RUST_ENV = {"RUSTC_BOOTSTRAP": "1", "RUSTFLAGS": RUST_FLAGS}
WARNINGS = [
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wconversion",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
]


def _run(
    command: list[str],
    directory: Path,
    name: str,
    *,
    extra_env: dict[str, str] | None = None,
    payload: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Execute an actual build/client and retain its output before asserting the expected exit.

    Parameters
    ----------
    command
        Direct compiler, Cargo, native client or profiling-tool vector.
    directory
        Exclusive profile build and log directory.
    name
        Diagnostic log stem.
    extra_env
        Test-only Rust instrumentation and profile output settings.
    payload
        Actual native CLI input stream, if required.

    Returns
    -------
    subprocess.CompletedProcess of bytes
        Actual program status and stdout/stderr for further observation.
    """
    env = dict(os.environ)
    if extra_env is not None:
        env.update(extra_env)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=payload,
        capture_output=True,
        timeout=90,
        check=False,
    )
    (directory / f"{name}.log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors="replace")
    return result


def _profile(directory: Path, name: str) -> dict[str, str]:
    """Select a unique genuine LLVM raw profile for one executed client.

    Parameters
    ----------
    directory
        Exclusive profile output directory.
    name
        Client name before its process-specific suffix.

    Returns
    -------
    dict of str to str
        Test-owned profile destination environment.
    """
    return {"LLVM_PROFILE_FILE": str(directory / f"{name}-%p.profraw")}


def test_original_rust_core_and_adapter_line_branch_coverage(tmp_path: Path) -> None:
    """Require measured full source coverage of unchanged Rust code and its C ABI boundary.

    Parameters
    ----------
    tmp_path
        Exclusive instrumented archives, native clients, raw profiles and LLVM report.
    """
    manifest = ROOT / "runtime/bare_metal/rust_kernel/Cargo.toml"
    core = ROOT / "controllers/rust/src/lib.rs"
    adapter = ROOT / "runtime/bare_metal/rust_kernel/src/lib.rs"
    source_bytes = {path: path.read_bytes() for path in [core, adapter]}
    version = _run(["rustc", "+1.98.1", "-vV"], tmp_path, "rust-version")
    assert version.stdout.startswith(b"rustc 1.98.1 ")
    host = next(
        line.removeprefix("host: ")
        for line in version.stdout.decode().splitlines()
        if line.startswith("host: ")
    )
    sysroot = Path(
        _run(["rustc", "+1.98.1", "--print", "sysroot"], tmp_path, "sysroot")
        .stdout.decode()
        .strip()
    )
    library = sysroot / "lib/rustlib" / host / "lib"
    profilers = list(library.glob("libprofiler_builtins-*.rlib"))
    assert len(profilers) == 1
    profiler = profilers[0]
    tools = sysroot / "lib/rustlib" / host / "bin"
    _run(
        [
            "cargo",
            "+1.98.1",
            "build",
            "--release",
            "--offline",
            "--locked",
            "--manifest-path",
            str(manifest),
            "--target-dir",
            str(tmp_path / "target"),
        ],
        tmp_path,
        "build-adapter",
        extra_env=RUST_ENV,
    )
    archive = tmp_path / "target/release/libwitness_amp_rust_kernel.a"
    runtime = ROOT / "tests/native/amp_rust_profile_runtime.c"
    compiler = ["gcc", "-std=gnu11", "-O2", *WARNINGS, "-Icontrollers/c"]
    for name, source_name in [
        ("api", "tests/native/controller_api_test.c"),
        ("cli", "controllers/c/controller_cli.c"),
    ]:
        _run(
            [
                *compiler,
                source_name,
                str(runtime),
                str(archive),
                str(profiler),
                "-Wl,--gc-sections",
                "-o",
                str(tmp_path / name),
            ],
            tmp_path,
            f"link-{name}",
        )
    trigger = tmp_path / "libpanic_trigger.rlib"
    _run(
        [
            "rustc",
            "+1.98.1",
            "--crate-type",
            "rlib",
            "--edition",
            "2024",
            "-C",
            "panic=abort",
            "-C",
            "instrument-coverage",
            "-Z",
            "coverage-options=branch",
            "-o",
            str(trigger),
            str(ROOT / "tests/native/amp_rust_profile_trigger.rs"),
        ],
        tmp_path,
        "build-panic-trigger",
        extra_env={"RUSTC_BOOTSTRAP": "1"},
    )
    _run(
        [
            *compiler,
            "tests/native/amp_rust_profile_trigger.c",
            str(runtime),
            str(trigger),
            str(archive),
            str(profiler),
            "-Wl,--gc-sections",
            "-o",
            str(tmp_path / "panic"),
        ],
        tmp_path,
        "link-panic",
    )
    _run([str(tmp_path / "api")], tmp_path, "api", extra_env=_profile(tmp_path, "api"))
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
    for mode in ["pid", "lqr"]:
        result = _run(
            [str(tmp_path / "cli"), mode],
            tmp_path,
            mode,
            extra_env=_profile(tmp_path, mode),
            payload=payload,
        )
        assert len(result.stdout.splitlines()) == len(rows) - 1
    panic = subprocess.run(
        [str(tmp_path / "panic")],
        cwd=ROOT,
        env={**os.environ, **_profile(tmp_path, "panic")},
        capture_output=True,
        timeout=10,
        check=False,
    )
    (tmp_path / "panic.log").write_bytes(panic.stdout + panic.stderr)
    assert panic.returncode == 42
    _run(
        [
            "cargo",
            "+1.98.1",
            "test",
            "--offline",
            "--locked",
            "--test",
            "controller_api",
            "--manifest-path",
            str(ROOT / "controllers/rust/Cargo.toml"),
            "--target-dir",
            str(tmp_path / "core-target"),
        ],
        tmp_path,
        "core-tests",
        extra_env={**RUST_ENV, **_profile(tmp_path, "core")},
    )
    core_tests = [
        path
        for path in (tmp_path / "core-target/debug/deps").glob("controller_api-*")
        if path.is_file() and os.access(path, os.X_OK)
    ]
    assert len(core_tests) == 1
    profiles = sorted(tmp_path.glob("*.profraw"))
    assert len(profiles) >= 5
    profile = tmp_path / "merged.profdata"
    _run(
        [str(tools / "llvm-profdata"), "merge", "-sparse", *map(str, profiles), "-o", str(profile)],
        tmp_path,
        "merge-profile",
    )
    exported = _run(
        [
            str(tools / "llvm-cov"),
            "export",
            str(tmp_path / "api"),
            f"-object={tmp_path / 'cli'}",
            f"-object={tmp_path / 'panic'}",
            f"-object={core_tests[0]}",
            f"-instr-profile={profile}",
        ],
        tmp_path,
        "coverage-export",
    )
    report = json.loads(exported.stdout)
    files: list[dict[str, Any]] = report["data"][0]["files"]
    for source_path in [core, adapter]:
        match = [item for item in files if Path(item["filename"]).resolve() == source_path]
        assert len(match) == 1
        summary = match[0]["summary"]
        for metric in ["lines", "regions", "functions", "branches"]:
            assert summary[metric]["count"] > 0
            assert summary[metric]["covered"] == summary[metric]["count"]
        assert source_path.read_bytes() == source_bytes[source_path]
