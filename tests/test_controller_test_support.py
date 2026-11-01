# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native controller test build modes

"""Build the real C controller program in its sanitized and its coverage mode."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from test_controller_parity import DEFAULT, oracle

from conftest import REPOSITORY_ROOT
from controller_test_support import C_COVERAGE_DIRECTORY, build_native_controllers

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

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
    program, rust = build_native_controllers(REPOSITORY_ROOT, tmp_path)
    assert program.parent == tmp_path
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
