# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — whole-frame readiness refusal through real native launch

"""Corrupt actual owned worker pipes before native admission, with bounded cleanup."""

from __future__ import annotations

import json
import os
import select
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from linux_load_readiness import MAX_READINESS_BYTES
from linux_load_trace_support import trace_command
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from linux_load_trace_support import OwnedTrace

__all__ = ["native_run"]


def _actual_worker(trace: OwnedTrace) -> tuple[int, int]:
    """Observe only live owned descendants, returning the worker's retained identity.

    Parameters
    ----------
    trace
        Tracer retaining verified parent/child relationships and pidfds.

    Returns
    -------
    tuple of int and int
        Actual production worker PID and its owned pidfd.
    """
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        trace.observe()
        for pid, descriptor in trace.descriptors.items():
            if select.select([descriptor], [], [], 0)[0]:
                continue
            try:
                command = Path(f"/proc/{pid}/cmdline").read_bytes()
            except FileNotFoundError:
                continue
            if b"linux_load_worker.py" in command:
                return pid, descriptor
        assert trace.process.poll() is None
        time.sleep(0.001)
    pytest.fail("actual production worker was not observed")


@pytest.mark.parametrize(
    "violation",
    [
        "partial",
        "oversized",
        "numeric_ready",
        "float_pid",
        "eof",
        "two_frames",
        "duplicate_ready",
        "duplicate_pid",
    ],
)
def test_real_startup_refusal(native_run: Path, tmp_path: Path, violation: str) -> None:
    """Refuse a malformed or incomplete actual pipe before native execution begins.

    Parameters
    ----------
    native_run
        Production controller and RTL plant executable, with real output paths.
    tmp_path
        Exclusive configuration, working data, trace and retained failure allocation.
    violation
        Actual pipe framing or field-type requirement to violate deliberately.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    workspace = tmp_path / "worker"
    with trace_command(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load.py"),
            "--profile",
            "cpu",
            "--cpu",
            str(min(os.sched_getaffinity(0))),
            "--journal",
            str(tmp_path / "load.json"),
            "--workspace",
            str(workspace),
            "--",
            str(native_run.resolve()),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "raw.csv"),
        ],
        "sched_getscheduler:delay_enter=2s:when=1",
        tmp_path / "readiness.strace",
    ) as trace:
        worker, descriptor = _actual_worker(trace)
        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        frame = json.dumps({"ready": True, "pid": worker}).encode()
        if violation == "partial":
            payload, expected = frame[:1], "timed out"
        elif violation == "oversized":
            payload, expected = b" " * MAX_READINESS_BYTES + b"\n", "frame limit"
        elif violation == "numeric_ready":
            payload = (json.dumps({"ready": 1, "pid": worker}) + "\n").encode()
            expected = "Boolean ready"
        elif violation == "float_pid":
            payload = (json.dumps({"ready": True, "pid": float(worker)}) + "\n").encode()
            expected = "positive integer"
        elif violation in {"duplicate_ready", "duplicate_pid"}:
            shadow = b'"ready":false,' if violation == "duplicate_ready" else b'"pid":0,'
            payload = frame.replace(b"{", b"{" + shadow, 1) + b"\n"
            expected = "duplicate JSON key"
        elif violation == "eof":
            payload, expected = frame, "readiness ended"
        else:
            payload, expected = frame + b"\n{}\n", "Extra data"
        with Path(f"/proc/{worker}/fd/1").open("wb", buffering=0) as pipe:
            assert pipe.write(payload) == len(payload)
        if violation == "eof":
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        stdout, stderr = trace.process.communicate(timeout=20)
        (tmp_path / "launcher.log").write_text(stdout + stderr, encoding="utf-8")
        assert trace.process.returncode == 1, stdout + stderr
        assert stdout == ""
        assert expected in stderr
        assert select.select([descriptor], [], [], 0)[0]
        assert (workspace / "worker.log").exists()
        assert not (workspace / "worker.json").exists()
        assert not (tmp_path / "load.json").exists()
        assert not (tmp_path / "events.bin").exists()
        assert not (tmp_path / "raw.csv").exists()
        assert "INJECTED" not in trace.log.read_text()
