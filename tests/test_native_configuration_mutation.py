# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — configuration integrity during actual run execution

"""Observe real output creation and change the actual configuration during a run."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


def wait_for_events(process: subprocess.Popen[str], events: Path) -> None:
    """Wait for the owned native controller to create its actual event output.

    Parameters
    ----------
    process
        Owned native controller whose exit must not be mistaken for readiness.
    events
        Exclusive event output created by that controller.
    """
    deadline = time.monotonic() + 5
    while not events.exists():
        assert time.monotonic() < deadline, "native controller did not create its event output"
        assert process.poll() is None, "native controller exited before creating its event output"
        time.sleep(0.001)


@pytest.mark.parametrize("mutation", ["overwrite", "replace", "append", "symlink"])
def test_configuration_changed_during_run(native_run: Path, tmp_path: Path, mutation: str) -> None:
    """Refuse changed configuration while retaining the actual completed run data.

    Parameters
    ----------
    native_run
        Production executable linked to an actual mechanical or thermal RTL plant.
    tmp_path
        Exclusive configuration, raw evidence and metadata allocation.
    mutation
        Actual overwrite, inode replacement, append or symlink substitution.
    """
    config = tmp_path / "run.conf"
    original = configuration("pid", "none").replace("pid 32", "pid 64")
    config.write_text(original, encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    process = subprocess.Popen(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_events(process, events)
        os.kill(process.pid, signal.SIGSTOP)
        observed, status = os.waitpid(process.pid, os.WUNTRACED)
        assert observed == process.pid
        assert os.WIFSTOPPED(status)
        assert os.WSTOPSIG(status) == signal.SIGSTOP
        assert events.exists()
        if mutation == "overwrite":
            config.write_text(original.replace("pid", "lqr", 1), encoding="utf-8")
        elif mutation == "replace":
            replacement = tmp_path / "replacement.conf"
            replacement.write_text(original.replace("pid", "lqr", 1), encoding="utf-8")
            replacement.replace(config)
        elif mutation == "append":
            with config.open("a", encoding="utf-8") as stream:
                stream.write(" ")
        else:
            saved = tmp_path / "original.conf"
            config.rename(saved)
            config.symlink_to(saved)
        os.kill(process.pid, signal.SIGCONT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 1
        assert stdout == ""
        expected = (
            "cannot hash actual regular artifact"
            if mutation == "symlink"
            else "native configuration changed during execution"
        )
        assert stderr.strip() == expected
        assert events.stat().st_size > 0
        assert events.stat().st_size % 16 == 0
        assert len(raw.read_text().splitlines()) == 65
        assert not metadata.exists()
    finally:
        process.send_signal(signal.SIGCONT)
        process.kill()
        process.communicate(timeout=5)
