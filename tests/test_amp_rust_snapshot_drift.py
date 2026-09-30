# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real owned Rust input drift during source/archive snapshots

"""Change test-owned original bytes at a real filesystem read and require capture refusal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from amp_rust_toolchain import TARGET, rust_toolchain
from amp_rust_vectors import ADAPTER, CORE

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def drift_interposer(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile a strict native shim that mutates only an explicitly selected owned file.

    Parameters
    ----------
    tmp_path_factory
        Exclusive compiler output allocation.

    Returns
    -------
    Path
        Actual native library forwarding opens to the real kernel syscall.
    """
    directory = tmp_path_factory.mktemp("rust-snapshot-drift-interposer")
    library = directory / "drift.so"
    result = subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-shared",
            "-fPIC",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-Wstrict-prototypes",
            "-Wmissing-prototypes",
            "-o",
            str(library),
            "tests/native/amp_rust_snapshot_drift.c",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return library


def _prepare_with_drift(
    source_root: Path,
    output: Path,
    original: Path,
    interposer: Path,
    env: dict[str, str],
) -> bytes:
    """Run the original Rust preparation against an owned input changed on its second read.

    Parameters
    ----------
    source_root
        Original Rust sources, copied into an owned tree for source-byte faults.
    output
        Exclusive preparation output directory.
    original
        Selected source or installed target library inside the test allocation.
    interposer
        Native real-syscall interposer used only for this child.
    env
        Actual compiler selection and optional isolated Rustup home.

    Returns
    -------
    bytes
        Actual refusal diagnostic for the caller's exact fault assertion.
    """
    assert original.resolve().is_relative_to(output.parent.resolve())
    output.mkdir()
    marker = output.parent / f"{output.name}.mutated"
    command = [
        sys.executable,
        "-c",
        (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); "
            "from amp_rust_build import prepare_rust_sources; "
            "prepare_rust_sources(Path(sys.argv[2]), Path(sys.argv[3]), 'rustc')"
        ),
        str(ROOT / "tools"),
        str(source_root),
        str(output),
    ]
    selected = {
        **os.environ,
        **env,
        "LD_PRELOAD": str(interposer),
        "WITNESS_DRIFT_PATH": str(original),
        "WITNESS_DRIFT_MARKER": str(marker),
    }
    result = subprocess.run(
        command, cwd=ROOT, env=selected, capture_output=True, timeout=90, check=False
    )
    (output.parent / f"{output.name}.log").write_bytes(result.stdout + result.stderr)
    assert result.returncode != 0
    assert marker.is_file()
    assert not (output / "rust_preparation.json").exists()
    return result.stderr


def test_original_source_changed_between_hash_and_copy_refused(
    tmp_path: Path, drift_interposer: Path
) -> None:
    """Refuse a real owned Cargo source changed after its hash and before its snapshot read.

    Parameters
    ----------
    tmp_path
        Exclusive copy of the original Rust source tree.
    drift_interposer
        Real-syscall byte mutation at the second file open.
    """
    owned = tmp_path / "original-source"
    for component in [CORE, ADAPTER]:
        for name in ["Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs"]:
            relative = Path(component) / name
            target = owned / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
    source = owned / CORE / "Cargo.toml"
    before = source.read_bytes()
    diagnostic = _prepare_with_drift(
        owned,
        tmp_path / "source-snapshot",
        source,
        drift_interposer,
        {},
    )
    assert b"Rust original source changed during snapshot" in diagnostic
    assert source.read_bytes() != before
    assert (ROOT / CORE / "Cargo.toml").read_bytes() == before


def test_original_target_archive_changed_between_hash_and_copy_refused(
    tmp_path: Path, drift_interposer: Path
) -> None:
    """Refuse an owned installed RV64 archive changed before its real snapshot copy.

    Parameters
    ----------
    tmp_path
        Exclusive actual Rustup compiler and target-library copy.
    drift_interposer
        Real-syscall byte mutation at the second file open.
    """
    selected = rust_toolchain("rustc")
    sysroot = Path(selected["compiler"]["path"]).parent.parent
    owned = tmp_path / "toolchain"
    (owned / "bin").mkdir(parents=True)
    for name in ["rustc", "cargo"]:
        shutil.copy2(sysroot / "bin" / name, owned / "bin" / name)
    host_library = owned / "lib"
    host_library.mkdir()
    for path in (sysroot / "lib").iterdir():
        if path.is_file() and not path.is_symlink():
            shutil.copy2(path, host_library / path.name)
        elif path.is_symlink():
            (host_library / path.name).symlink_to(path.readlink())
    target = host_library / "rustlib" / TARGET / "lib"
    target.mkdir(parents=True)
    for name in selected["target_libraries"]:
        original = Path(name)
        shutil.copy2(original, target / original.name)
    rustup = shutil.which("rustup")
    assert rustup is not None
    env = {"RUSTUP_HOME": str(tmp_path / "rustup-home")}
    linked = subprocess.run(
        [rustup, "toolchain", "link", "witness-snapshot-drift", str(owned)],
        env={**os.environ, **env},
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert linked.returncode == 0, linked.stderr.decode(errors="replace")
    env["RUSTUP_TOOLCHAIN"] = "witness-snapshot-drift"
    archive = next(target.glob("liballoc-*.rlib"))
    before = archive.read_bytes()
    diagnostic = _prepare_with_drift(
        ROOT,
        tmp_path / "archive-snapshot",
        archive,
        drift_interposer,
        env,
    )
    assert b"Rust original target library changed during snapshot" in diagnostic
    assert archive.read_bytes() != before
    original = next(
        Path(name) for name in selected["target_libraries"] if name.endswith(archive.name)
    )
    assert sha256_of_file(original) == selected["target_libraries"][str(original)]
