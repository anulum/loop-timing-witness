# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — traced host source-checker process lifetime

"""Run the real traced host launcher and check completion, deadline and cleanup."""

from __future__ import annotations

import hashlib
import platform
import shutil
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.neural_checker_execution import invoke_source_checker
from loop_timing_witness.neural_checker_installation import (
    CheckerInstalledFile,
    NeuralCheckerInstallation,
)

if TYPE_CHECKING:
    from types import FrameType


def _installation(root: Path, tracer: str = "strace") -> NeuralCheckerInstallation:
    """Select the running interpreter and one actual tracer program.

    Parameters
    ----------
    root
        Existing import root.
    tracer
        Program name found on the search path.

    Returns
    -------
    NeuralCheckerInstallation
        Real host installation metadata.
    """
    program = shutil.which(tracer)
    assert program is not None
    files = []
    for name, path in (
        ("interpreter/python", Path(sys.executable).resolve()),
        ("tracer/program", Path(program).resolve()),
    ):
        raw = path.read_bytes()
        files.append(CheckerInstalledFile(name, path, hashlib.sha256(raw).hexdigest(), len(raw)))
    return NeuralCheckerInstallation(
        files[0], files[1], tuple(files), (root,), platform.platform(), platform.release()
    )


def _script(tmp_path: Path, body: str) -> tuple[Path, Path]:
    """Write a source program and an empty invocation directory.

    Parameters
    ----------
    tmp_path
        Owned directory.
    body
        Program text.

    Returns
    -------
    tuple[Path, Path]
        Program and invocation directory.
    """
    script = tmp_path / "checker.py"
    script.write_text(body, encoding="utf-8")
    directory = tmp_path / "check"
    directory.mkdir()
    return script, directory


def test_completed_traced_program_returns_logs_trace_and_observation(tmp_path: Path) -> None:
    """Return the native status, both logs, the trace and the worker observation.

    Parameters
    ----------
    tmp_path
        Owned program and invocation directory.
    """
    script, directory = _script(tmp_path, "print('compared')\n")
    actual = invoke_source_checker(_installation(tmp_path), script, "check", directory)
    assert actual.returncode == 0
    assert actual.stdout == b"compared\n"
    assert actual.stderr == b""
    assert b"openat" in actual.trace
    assert actual.observation is not None
    assert actual.observation["phase"] == "source"
    assert actual.interrupted is False
    assert actual.completed_ns >= actual.started_ns


def test_deadline_kills_and_reaps_the_whole_group(tmp_path: Path) -> None:
    """Interrupt a program at its deadline without inventing an observation.

    Parameters
    ----------
    tmp_path
        Owned program and invocation directory.
    """
    script, directory = _script(tmp_path, "import time\ntime.sleep(60)\n")
    actual = invoke_source_checker(
        _installation(tmp_path), script, "check", directory, deadline_seconds=1
    )
    assert actual.interrupted is True
    assert actual.returncode == -signal.SIGKILL
    assert actual.observation is None


def test_interrupted_parent_reaps_the_group_and_reraises(tmp_path: Path) -> None:
    """Kill the program group when the waiting parent is interrupted.

    Parameters
    ----------
    tmp_path
        Owned program and invocation directory.
    """
    script, directory = _script(
        tmp_path, "import pathlib, time\npathlib.Path('started').touch()\ntime.sleep(60)\n"
    )

    def interrupt(number: int, frame: FrameType | None) -> None:
        """Raise a keyboard interrupt from the alarm.

        Parameters
        ----------
        number, frame
            Signal details.

        Raises
        ------
        KeyboardInterrupt
            Always.
        """
        del number, frame
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGALRM, interrupt)
    signal.alarm(2)
    try:
        with pytest.raises(KeyboardInterrupt):
            invoke_source_checker(_installation(tmp_path), script, "check", directory)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    assert (directory / "started").exists()


def test_missing_trace_and_observation_are_reported_as_absent(tmp_path: Path) -> None:
    """Return no trace and no observation when the selected tracer runs nothing.

    Parameters
    ----------
    tmp_path
        Owned program and invocation directory.
    """
    script, directory = _script(tmp_path, "print('never')\n")
    actual = invoke_source_checker(_installation(tmp_path, "true"), script, "check", directory)
    assert actual.returncode == 0
    assert actual.trace == b""
    assert actual.observation is None


def test_observation_beyond_its_allocation_is_not_decoded(tmp_path: Path) -> None:
    """Ignore an observation whose resolved size exceeds the allocation.

    Parameters
    ----------
    tmp_path
        Owned program, invocation directory and sparse oversized file.
    """
    large = tmp_path / "large.json"
    with large.open("wb") as stream:
        stream.truncate(1048577)
    body = f"import os\nos.symlink({str(large)!r}, 'checker-observation.json')\nos._exit(0)\n"
    script, directory = _script(tmp_path, body)
    actual = invoke_source_checker(_installation(tmp_path), script, "check", directory)
    assert actual.returncode == 0
    assert actual.observation is None
    assert (directory / "checker-observation.json").is_symlink()
