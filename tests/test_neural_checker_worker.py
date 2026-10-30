# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — isolated source-checker worker process

"""Run the actual worker module as a process and read its observation."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _run(tmp_path: Path, body: str, *roots: Path) -> tuple[subprocess.CompletedProcess[str], Any]:
    """Run one source program through the worker.

    Parameters
    ----------
    tmp_path
        Owned working directory.
    body
        Source program text.
    *roots
        Import roots passed to the worker.

    Returns
    -------
    tuple[subprocess.CompletedProcess[str], Any]
        Process result and decoded observation, or ``None`` when none was written.
    """
    script = tmp_path / "checker.py"
    script.write_text(body, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "loop_timing_witness.neural_checker_worker",
            str(script),
            "check",
            *(str(root) for root in roots),
        ],
        cwd=work,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    path = work / "checker-observation.json"
    return result, json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def test_completed_source_program_records_argv_modules_and_files(tmp_path: Path) -> None:
    """Record the fixed argv, imported modules and every observed file.

    Parameters
    ----------
    tmp_path
        Owned working directory and import root.
    """
    root = tmp_path / "imports"
    root.mkdir()
    (root / "probe_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    result, observation = _run(tmp_path, "import sys\nimport probe_module\nprint(sys.argv)\n", root)
    assert result.returncode == 0, result.stderr
    assert observation["schema_id"] == "loop-timing-witness.sc-checker-worker-observation.v1"
    assert observation["phase"] == "source"
    assert observation["native_returncode"] == 0
    script = str(tmp_path / "checker.py")
    assert observation["actual_argv"] == [script, "--check", "--steps", "1000", "--seed", "42"]
    assert {"name": "probe_module", "path": str(root / "probe_module.py")} in observation["modules"]
    paths = {item["path"] for item in observation["files"]}
    assert {script, str(root / "probe_module.py")} <= paths
    assert observation["completed_ns"] >= observation["started_ns"]


@pytest.mark.parametrize(
    ("body", "status"),
    [("raise SystemExit(4)\n", 4), ("raise SystemExit('stop')\n", 1)],
)
def test_source_exit_status_is_recorded(tmp_path: Path, body: str, status: int) -> None:
    """Record an integer exit status and map any other exit value to failure.

    Parameters
    ----------
    tmp_path
        Owned working directory.
    body
        Program that exits.
    status
        Expected worker and recorded status.
    """
    result, observation = _run(tmp_path, body)
    assert result.returncode == status
    assert observation["native_returncode"] == status
    assert observation["phase"] == "source"


def test_refused_source_operation_reports_a_fixed_diagnostic(tmp_path: Path) -> None:
    """Report an operating-system or value refusal without its traceback.

    Parameters
    ----------
    tmp_path
        Owned working directory.
    """
    result, observation = _run(tmp_path, "raise ValueError('denied')\n")
    assert result.returncode == 1
    assert result.stderr == "Source checker execution or isolation was refused.\n"
    assert observation["native_returncode"] == 1


def test_unexpected_source_failure_still_writes_its_observation(tmp_path: Path) -> None:
    """Fail closed on an unexpected exception and keep the observation.

    Parameters
    ----------
    tmp_path
        Owned working directory.
    """
    result, observation = _run(tmp_path, "raise RuntimeError('broken')\n")
    assert result.returncode == 1
    assert result.stderr == "Source checker execution failed.\n"
    assert "Traceback" not in result.stderr
    assert observation["native_returncode"] == 1
    assert observation["phase"] == "source"


def test_excessive_observed_runtime_file_refuses_the_observation(tmp_path: Path) -> None:
    """Refuse to hash a mapped file beyond the observation allocation.

    Parameters
    ----------
    tmp_path
        Owned working directory; the large file is sparse.
    """
    large = tmp_path / "large.bin"
    with large.open("wb") as stream:
        stream.truncate(256 * 1024 * 1024 + 1)
    body = (
        "import mmap, sys\n"
        f"stream = open({str(large)!r}, 'rb')\n"
        "sys.keep = (stream, mmap.mmap(stream.fileno(), 4096, access=mmap.ACCESS_READ))\n"
    )
    result, observation = _run(tmp_path, body)
    assert result.returncode == 1
    assert result.stderr == "Source checker execution failed.\n"
    assert observation is None


def test_unnamed_mapping_is_not_an_observed_file(tmp_path: Path) -> None:
    """Skip a mapped object that has a path-like name but no file.

    Parameters
    ----------
    tmp_path
        Owned working directory.
    """
    body = (
        "import mmap, os, sys\n"
        "descriptor = os.memfd_create('checker-scratch')\n"
        "os.ftruncate(descriptor, 4096)\n"
        "sys.keep = mmap.mmap(descriptor, 4096)\n"
    )
    result, observation = _run(tmp_path, body)
    assert result.returncode == 0, result.stderr
    assert not any("memfd" in item["path"] for item in observation["files"])


def test_importing_the_worker_does_not_run_it() -> None:
    """Import the worker module without executing a source program."""
    module = importlib.import_module("loop_timing_witness.neural_checker_worker")
    assert callable(module.main)
