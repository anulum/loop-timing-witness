# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native controller test build modes

"""Build the real C and Rust controller programs in their ordinary and coverage modes."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from test_controller_parity import DEFAULT, oracle

from conftest import REPOSITORY_ROOT
from controller_test_support import (
    C_COVERAGE_DIRECTORY,
    RUST_COVERAGE_DIRECTORY,
    build_native_controllers,
    build_rust_controller,
)

if TYPE_CHECKING:
    from pathlib import Path

SANITIZER = b"__ubsan_handle"
SAMPLE = "0,16777216,0,0"


def test_ordinary_build_keeps_the_sanitizer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build in the managed directory with undefined-behaviour refusal and no counters.

    Parameters
    ----------
    tmp_path
        Managed executable directory.
    monkeypatch
        Restoring manager for the coverage environment.
    """
    monkeypatch.delenv(C_COVERAGE_DIRECTORY, raising=False)
    monkeypatch.delenv(RUST_COVERAGE_DIRECTORY, raising=False)
    program, rust = build_native_controllers(REPOSITORY_ROOT, tmp_path)
    assert program.parent == tmp_path
    assert rust == REPOSITORY_ROOT / "controllers/rust/target/release/witness-controller"
    assert rust.is_file()
    assert SANITIZER in program.read_bytes()
    assert not list(tmp_path.glob("*.gcno"))


def test_coverage_build_collects_counters_in_the_named_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build in the coverage directory with counters and without the sanitizer.

    Parameters
    ----------
    tmp_path
        Owned managed and coverage directories.
    monkeypatch
        Restoring manager for the coverage environment.
    """
    coverage = tmp_path / "coverage" / "nested"
    monkeypatch.setenv(C_COVERAGE_DIRECTORY, str(coverage))
    program, _ = build_native_controllers(REPOSITORY_ROOT, tmp_path / "managed")
    assert program == coverage / "controller_cli"
    assert SANITIZER not in program.read_bytes()
    notes = {path.name for path in coverage.glob("*.gcno")}
    assert notes == {"controller_cli-witness_controller.gcno", "controller_cli-controller_cli.gcno"}
    result = subprocess.run(
        [str(program), "pid"],
        input=",".join(map(str, DEFAULT)) + "\n" + SAMPLE + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == oracle("pid", DEFAULT, [SAMPLE])
    counters = {path.name for path in coverage.glob("*.gcda")}
    assert counters == {
        "controller_cli-witness_controller.gcda",
        "controller_cli-controller_cli.gcda",
    }


def test_rust_coverage_build_writes_profiles_where_the_caller_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Build an instrumented Rust program in the named directory; each run writes a profile.

    Parameters
    ----------
    tmp_path
        Owned coverage and profile directories.
    monkeypatch
        Restoring manager for the coverage environment.
    """
    coverage = tmp_path / "rust-coverage"
    monkeypatch.setenv(RUST_COVERAGE_DIRECTORY, str(coverage))
    program = build_rust_controller(REPOSITORY_ROOT)
    assert program.is_relative_to(coverage / "target")
    assert program.name == "witness-controller"
    assert b"__llvm_profile" in program.read_bytes()
    profiles = tmp_path / "profiles"
    result = subprocess.run(
        [str(program), "pid"],
        input=",".join(map(str, DEFAULT)) + "\n" + SAMPLE + "\n",
        capture_output=True,
        text=True,
        check=False,
        env={"LLVM_PROFILE_FILE": str(profiles / "run-%p.profraw")},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == oracle("pid", DEFAULT, [SAMPLE])
    assert len(list(profiles.glob("run-*.profraw"))) == 1


def test_rust_coverage_build_refuses_a_build_without_an_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Cargo stand-in that reports no executable cannot supply the coverage program.

    Parameters
    ----------
    tmp_path
        Owned stand-in and coverage directories.
    monkeypatch
        Restoring manager for the environment.
    """
    stand_in = tmp_path / "bin" / "cargo"
    stand_in.parent.mkdir()
    stand_in.write_text(
        '#!/bin/sh\necho \'{"reason": "build-finished", "success": true}\'\n',
        encoding="utf-8",
    )
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stand_in.parent}:/usr/bin:/bin")
    monkeypatch.setenv(RUST_COVERAGE_DIRECTORY, str(tmp_path / "coverage"))
    with pytest.raises(RuntimeError, match=r"^Cargo reported no Rust controller executable$"):
        build_rust_controller(REPOSITORY_ROOT)
