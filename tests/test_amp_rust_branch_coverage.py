# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — measured Rust safe-core and C ABI statement/branch coverage

"""Profile original Rust APIs through native C/Rust clients, core tests and a host panic."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from loop_timing_witness.host_profile import scaled

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
        timeout=scaled(90),
        check=False,
    )
    (directory / f"{name}.log").write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors="replace")
    return result


def cargo_artifact(stdout: str, name: str, *, executable: bool) -> Path:
    """Return the one file Cargo reports for a built target, wherever its layout puts it.

    Parameters
    ----------
    stdout
        Standard output of a Cargo command run with ``--message-format=json``;
        lines that are not JSON messages, such as test output, are skipped.
    name
        Cargo target name.
    executable
        Select the target's executable when true, else its ``.rlib`` archive.

    Returns
    -------
    Path
        The single file of that kind among the target's compiler artifacts; an
        executable is also required to be runnable.
    """
    found: set[str] = set()
    for line in stdout.splitlines():
        if not line.startswith("{"):
            continue
        message: dict[str, Any] = json.loads(line)
        if message.get("reason") != "compiler-artifact" or message["target"]["name"] != name:
            continue
        if executable:
            if message["executable"] is not None:
                found.add(message["executable"])
        else:
            found.update(path for path in message["filenames"] if path.endswith(".rlib"))
    assert len(found) == 1, sorted(found)
    path = Path(found.pop())
    assert path.is_file()
    if executable:
        assert os.access(path, os.X_OK)
    return path


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


_CLIENT_FLAGS = [
    "--edition=2024",
    "-C",
    "panic=abort",
    "-C",
    "opt-level=3",
    "-C",
    "instrument-coverage",
    "-Z",
    "coverage-options=branch",
    "-D",
    "warnings",
    "-D",
    "unsafe_code",
]
_COEFFICIENTS = (
    "2147483647,2147483647,16777216,2147483647,-2147483648,2147483647,"
    "-2147483648,-2147483648,2147483647,-2147483648,2147483647"
)
_ROWS = [
    "0,2147483647,-2147483648,2147483647",
    "1,-2147483648,2147483647,-2147483648",
    "2,0,-1,-1",
    "3,0,1,1",
    "reset",
    "0,16777216,0,0",
    "1,0,0,0",
]
_COMPILER = ["gcc", "-std=gnu11", "-O2", *WARNINGS, "-Icontrollers/c"]
_RUNTIME = ROOT / "tests/native/amp_rust_profile_runtime.c"


def _rust_consumer(directory: Path, source: Path, library: Path) -> Path:
    """Build and exercise a real public Rust client of the original release library.

    Parameters
    ----------
    directory
        Exclusive original release archive, native clients and profiles.
    source
        Complete source of the public state-reset consumer.
    library
        Instrumented controller library archive that Cargo built for the adapter.

    Returns
    -------
    Path
        Executed binary whose active mapping joins the complete original profile set.
    """
    rust_client = directory / "rust-client"
    rust_arguments = [
        *_CLIENT_FLAGS,
        "--extern",
        f"witness_controller={library}",
        "-L",
        f"dependency={library.parent}",
        str(source),
    ]
    _run(
        ["rustfmt", "+1.100.0", "--edition", "2024", "--check", str(source)],
        directory,
        "rust-client-format",
    )
    _run(
        ["rustc", "+1.100.0", *rust_arguments, "-o", str(rust_client)],
        directory,
        "rust-client-build",
        extra_env={"RUSTC_BOOTSTRAP": "1"},
    )
    _clippy_client(directory, rust_arguments)
    consumed = _run(
        [str(rust_client)],
        directory,
        "rust-client",
        extra_env=_profile(directory, "rust-client"),
    )
    assert consumed.stdout == b"original release Rust API reset verified\n"
    return rust_client


def _clippy_client(directory: Path, rust_arguments: list[str]) -> None:
    """Require a clean strict Clippy pass over the Rust client.

    Parameters
    ----------
    directory
        Exclusive build and log directory.
    rust_arguments
        Compiler arguments of the client build.
    """
    _run(
        [
            "rustup",
            "run",
            "1.100.0",
            "clippy-driver",
            *rust_arguments,
            "--emit=metadata",
            "-D",
            "clippy::all",
            "-o",
            str(directory / "rust-client-clippy.rmeta"),
        ],
        directory,
        "rust-client-clippy",
        extra_env={"RUSTC_BOOTSTRAP": "1"},
    )


def test_original_rust_core_and_adapter_line_branch_coverage(tmp_path: Path) -> None:
    """Require measured full source coverage of unchanged Rust code and its C ABI boundary.

    Parameters
    ----------
    tmp_path
        Exclusive instrumented archives, native clients, raw profiles and LLVM report.
    """
    core = ROOT / "controllers/rust/src/lib.rs"
    adapter = ROOT / "runtime/bare_metal/rust_kernel/src/lib.rs"
    consumer = ROOT / "tests/native/amp_rust_reset_client.rs"
    source_bytes = {path: path.read_bytes() for path in [core, adapter, consumer]}
    profiler, tools = _pinned_toolchain(tmp_path)
    archive, library = _instrumented_adapter(tmp_path)
    rust_client = _rust_consumer(tmp_path, consumer, library)
    _link_c_clients(tmp_path, archive, profiler)
    _link_panic_client(tmp_path, archive, profiler)
    _exercise_c_clients(tmp_path)
    core_tests = _core_tests(tmp_path)
    objects = [rust_client, tmp_path / "api", tmp_path / "cli", tmp_path / "panic", core_tests]
    files = _coverage_files(tmp_path, tools, objects)
    for source_path in [core, adapter, consumer]:
        match = [item for item in files if Path(item["filename"]).resolve() == source_path]
        assert len(match) == 1
        summary = match[0]["summary"]
        for metric in ["lines", "regions", "functions", "branches", "instantiations"]:
            if source_path != consumer or metric != "branches":
                assert summary[metric]["count"] > 0
            assert summary[metric]["covered"] == summary[metric]["count"]
        assert source_path.read_bytes() == source_bytes[source_path]


def _pinned_toolchain(directory: Path) -> tuple[Path, Path]:
    """Require the pinned Rust toolchain and return its profiler runtime and LLVM tools.

    Parameters
    ----------
    directory
        Exclusive log directory.

    Returns
    -------
    tuple[Path, Path]
        The one host ``profiler_builtins`` archive and the LLVM tool directory.
    """
    version = _run(["rustc", "+1.100.0", "-vV"], directory, "rust-version")
    assert version.stdout.startswith(b"rustc 1.100.0 ")
    host = next(
        line.removeprefix("host: ")
        for line in version.stdout.decode().splitlines()
        if line.startswith("host: ")
    )
    sysroot = Path(
        _run(["rustc", "+1.100.0", "--print", "sysroot"], directory, "sysroot")
        .stdout.decode()
        .strip()
    )
    library = sysroot / "lib/rustlib" / host / "lib"
    profilers = list(library.glob("libprofiler_builtins-*.rlib"))
    assert len(profilers) == 1
    return profilers[0], sysroot / "lib/rustlib" / host / "bin"


def _instrumented_adapter(directory: Path) -> tuple[Path, Path]:
    """Build the adapter archive and the core library with branch instrumentation.

    Parameters
    ----------
    directory
        Exclusive Cargo target and log directory.

    Returns
    -------
    tuple[Path, Path]
        Adapter static archive and the ``witness_controller`` library Cargo reports.
    """
    built = _run(
        [
            "cargo",
            "+1.100.0",
            "build",
            "--release",
            "--offline",
            "--locked",
            "--message-format=json",
            "--manifest-path",
            str(ROOT / "runtime/bare_metal/rust_kernel/Cargo.toml"),
            "--target-dir",
            str(directory / "target"),
        ],
        directory,
        "build-adapter",
        extra_env=RUST_ENV,
    )
    archive = directory / "target/release/libwitness_amp_rust_kernel.a"
    library = cargo_artifact(built.stdout.decode(), "witness_controller", executable=False)
    return archive, library


def _link_c_clients(directory: Path, archive: Path, profiler: Path) -> None:
    """Link the C API test and the controller CLI with the instrumented adapter.

    Parameters
    ----------
    directory
        Exclusive output and log directory.
    archive
        Instrumented adapter archive.
    profiler
        Rust profiler runtime archive.
    """
    for name, source_name in [
        ("api", "tests/native/controller_api_test.c"),
        ("cli", "controllers/c/controller_cli.c"),
    ]:
        _run(
            [
                *_COMPILER,
                source_name,
                str(_RUNTIME),
                str(archive),
                str(profiler),
                "-Wl,--gc-sections",
                "-o",
                str(directory / name),
            ],
            directory,
            f"link-{name}",
        )


def _link_panic_client(directory: Path, archive: Path, profiler: Path) -> None:
    """Build the instrumented panic trigger and link the C client that calls it.

    Parameters
    ----------
    directory
        Exclusive output and log directory.
    archive
        Instrumented adapter archive.
    profiler
        Rust profiler runtime archive.
    """
    trigger = directory / "libpanic_trigger.rlib"
    _run(
        [
            "rustc",
            "+1.100.0",
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
        directory,
        "build-panic-trigger",
        extra_env={"RUSTC_BOOTSTRAP": "1"},
    )
    _run(
        [
            *_COMPILER,
            "tests/native/amp_rust_profile_trigger.c",
            str(_RUNTIME),
            str(trigger),
            str(archive),
            str(profiler),
            "-Wl,--gc-sections",
            "-o",
            str(directory / "panic"),
        ],
        directory,
        "link-panic",
    )


def _exercise_c_clients(directory: Path) -> None:
    """Run the C API test, both CLI modes on extreme inputs and the panic client.

    Parameters
    ----------
    directory
        Directory of the linked clients, their profiles and logs.
    """
    _run([str(directory / "api")], directory, "api", extra_env=_profile(directory, "api"))
    payload = (_COEFFICIENTS + "\n" + "\n".join(_ROWS) + "\n").encode()
    for mode in ["pid", "lqr"]:
        result = _run(
            [str(directory / "cli"), mode],
            directory,
            mode,
            extra_env=_profile(directory, mode),
            payload=payload,
        )
        assert len(result.stdout.splitlines()) == len(_ROWS) - 1
    panic = subprocess.run(
        [str(directory / "panic")],
        cwd=ROOT,
        env={**os.environ, **_profile(directory, "panic")},
        capture_output=True,
        timeout=scaled(10),
        check=False,
    )
    (directory / "panic.log").write_bytes(panic.stdout + panic.stderr)
    assert panic.returncode == 42


def _core_tests(directory: Path) -> Path:
    """Run the instrumented core API tests and return their test executable.

    Parameters
    ----------
    directory
        Exclusive Cargo target, profile and log directory.

    Returns
    -------
    Path
        Core API test executable.
    """
    core_run = _run(
        [
            "cargo",
            "+1.100.0",
            "test",
            "--offline",
            "--locked",
            "--message-format=json",
            "--test",
            "controller_api",
            "--manifest-path",
            str(ROOT / "controllers/rust/Cargo.toml"),
            "--target-dir",
            str(directory / "core-target"),
        ],
        directory,
        "core-tests",
        extra_env={**RUST_ENV, **_profile(directory, "core")},
    )
    return cargo_artifact(core_run.stdout.decode(), "controller_api", executable=True)


def _coverage_files(directory: Path, tools: Path, objects: list[Path]) -> list[dict[str, Any]]:
    """Merge every raw profile and export the LLVM coverage of the instrumented objects.

    Parameters
    ----------
    directory
        Directory of the raw profiles and logs.
    tools
        LLVM tool directory of the pinned toolchain.
    objects
        Main executable first, then every other instrumented object.

    Returns
    -------
    list[dict[str, Any]]
        Per-file coverage records of the export.
    """
    profiles = sorted(directory.glob("*.profraw"))
    assert len(profiles) >= 6
    profile = directory / "merged.profdata"
    _run(
        [str(tools / "llvm-profdata"), "merge", "-sparse", *map(str, profiles), "-o", str(profile)],
        directory,
        "merge-profile",
    )
    exported = _run(
        [
            str(tools / "llvm-cov"),
            "export",
            str(objects[0]),
            *[f"-object={path}" for path in objects[1:]],
            f"-instr-profile={profile}",
        ],
        directory,
        "coverage-export",
    )
    report = json.loads(exported.stdout)
    files: list[dict[str, Any]] = report["data"][0]["files"]
    return files
