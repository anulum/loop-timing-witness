# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public native load launch API refusal and receipt paths

"""Exercise real native execution and public launch refusals before resource allocation."""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from linux_load import LoadExecution, execute_with_load
from linux_load_config import LoadConfiguration
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


@pytest.mark.parametrize(
    "violation",
    [
        "empty",
        "short_timeout",
        "long_timeout",
        "relative",
        "missing",
        "directory",
        "permission",
        "journal",
        "symlink",
        "workspace",
    ],
)
def test_launch_refusal(native_run: Path, tmp_path: Path, violation: str) -> None:
    """Refuse actual path/argument conflicts before launching any owned child.

    Parameters
    ----------
    native_run
        Actual production native executable.
    tmp_path
        Exclusive conflict and output allocation.
    violation
        Public command, lifetime or filesystem requirement to violate.
    """
    program = tmp_path / "nonexecutable"
    program.write_bytes(b"owner bytes")
    journal, workspace = tmp_path / "load.json", tmp_path / "worker"
    command = [str(native_run.resolve())]
    timeout = 120.0
    if violation == "empty":
        command = []
    elif violation in {"short_timeout", "long_timeout"}:
        timeout = 0 if violation == "short_timeout" else 3601
    elif violation in {"relative", "missing", "directory", "permission"}:
        command = [
            {
                "relative": "relative-executable",
                "missing": str(tmp_path / "missing"),
                "directory": str(tmp_path),
                "permission": str(program),
            }[violation]
        ]
    elif violation == "journal":
        journal.write_bytes(b"preserve journal")
    elif violation == "symlink":
        journal.symlink_to(tmp_path / "missing")
    else:
        workspace.mkdir()
        (workspace / "owner.txt").write_bytes(b"preserve workspace")
    with (
        (tmp_path / "stdout.log").open("xb") as stream,
        pytest.raises(
            (ValueError, FileExistsError), match=r"command|timeout|executable|journal|File exists"
        ),
    ):
        execute_with_load(
            command,
            LoadConfiguration("cpu", min(os.sched_getaffinity(0))),
            LoadExecution(journal, workspace, timeout),
            stream,
        )
    if violation == "workspace":
        assert (workspace / "owner.txt").read_bytes() == b"preserve workspace"
    else:
        assert not workspace.exists()
    if violation == "journal":
        assert journal.read_bytes() == b"preserve journal"
    if violation == "symlink":
        assert journal.is_symlink()
    assert program.read_bytes() == b"owner bytes"


@pytest.mark.parametrize("failure", ["worker_source", "native_format", "journal_parent"])
def test_actual_launch_io_failure(native_run: Path, tmp_path: Path, failure: str) -> None:
    """Retain failures from real worker exec, native exec or exclusive journal creation.

    Parameters
    ----------
    native_run
        Production controller and actual plant/AXI executable.
    tmp_path
        Exclusive working files and partial outputs.
    failure
        Actual absent worker source, invalid executable format or journal parent.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    command = [
        str(native_run.resolve()),
        str(config),
        str(tmp_path / "events.bin"),
        str(tmp_path / "raw.csv"),
    ]
    workspace = tmp_path / "worker"
    journal = (
        tmp_path / "missing/load.json" if failure == "journal_parent" else tmp_path / "load.json"
    )
    source = tmp_path / "missing.py" if failure == "worker_source" else None
    if failure == "native_format":
        program = tmp_path / "invalid_elf"
        program.write_bytes(b"invalid executable format")
        program.chmod(0o700)
        command[0] = str(program)
    expected = ValueError if failure == "worker_source" else OSError
    with (
        (tmp_path / "stdout.log").open("xb") as stream,
        pytest.raises(expected, match=r"readiness ended|Exec format|No such file"),
    ):
        execute_with_load(
            command,
            LoadConfiguration("cpu", min(os.sched_getaffinity(0))),
            LoadExecution(journal, workspace, worker_path=source),
            stream,
        )
    assert not journal.exists()
    assert (workspace / "worker.log").exists()
    if failure == "worker_source":
        assert "can't open file" in (workspace / "worker.log").read_text()
    if failure == "journal_parent":
        receipt = json.loads((workspace / "worker.json").read_bytes())
        with pytest.raises(ProcessLookupError):
            os.kill(receipt["worker_pid"], 0)
        assert (tmp_path / "events.bin").stat().st_size > 0
        assert (tmp_path / "stdout.log").read_text().startswith("simulation_only ")


def test_actual_worker_receipt_failure(native_run: Path, tmp_path: Path) -> None:
    """Reject worker completion failure even after the real native controller succeeds.

    Parameters
    ----------
    native_run
        Actual production native controller and plant/AXI model.
    tmp_path
        Exclusive workspace, raw outputs and owner-created receipt conflict.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    workspace = tmp_path / "worker"
    journal = tmp_path / "load.json"

    def create_conflict() -> None:
        """Create a real exclusive receipt collision after workspace allocation."""
        deadline = time.monotonic() + 5
        while not (workspace / "worker.log").exists() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert (workspace / "worker.log").exists()
        with (workspace / "worker.json").open("xb") as stream:
            stream.write(b"preserve owner bytes")

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(create_conflict)
        with (
            (tmp_path / "stdout.log").open("xb") as stream,
            pytest.raises(subprocess.CalledProcessError),
        ):
            execute_with_load(
                [
                    str(native_run.resolve()),
                    str(config),
                    str(tmp_path / "events.bin"),
                    str(tmp_path / "raw.csv"),
                ],
                LoadConfiguration("cpu", min(os.sched_getaffinity(0))),
                LoadExecution(journal, workspace),
                stream,
            )
        pending.result(timeout=5)
    assert (workspace / "worker.json").read_bytes() == b"preserve owner bytes"
    assert "File exists" in (workspace / "worker.log").read_text()
    assert (tmp_path / "stdout.log").read_text().startswith("simulation_only ")
    assert not journal.exists()
