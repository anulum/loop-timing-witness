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
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from linux_load_readiness import MAX_READINESS_BYTES
from linux_load_trace_support import trace_command
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled

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
    # Coverage starts the launcher before strace can observe its worker creation.
    # The production readiness timeout and syscall delay are unchanged.
    deadline = time.monotonic() + scaled(30)
    found: tuple[int, int] | None = None
    while found is None and time.monotonic() < deadline:
        trace.observe()
        for pid, descriptor in trace.descriptors.items():
            if select.select([descriptor], [], [], 0)[0]:
                continue
            with suppress(FileNotFoundError, ProcessLookupError):
                command = Path(f"/proc/{pid}/cmdline").read_bytes()
                if b"linux_load_worker.py" in command:
                    found = pid, descriptor
                    break
        if found is None:
            assert trace.process.poll() is None
            time.sleep(0.001)
    assert found is not None, "actual production worker was not observed"
    return found


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
        _cpu_load_command(native_run, config, tmp_path),
        "sched_getscheduler:delay_enter=2s:when=1",
        tmp_path / "readiness.strace",
    ) as trace:
        worker, descriptor = _actual_worker(trace)
        # The delayed scheduler query keeps the worker from reporting readiness itself. A
        # group stop holds it longer for the cases the launcher refuses later; the eof case
        # kills it at once instead, because a kill that follows a group stop can reach strace
        # during its PTRACE_LISTEN, which then fails with EIO and ends the trace.
        if violation != "eof":
            signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        payload, expected = _readiness_frame(violation, worker)
        with Path(f"/proc/{worker}/fd/1").open("wb", buffering=0) as pipe:
            assert pipe.write(payload) == len(payload)
        if violation == "eof":
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        stdout, stderr = trace.process.communicate(timeout=scaled(20))
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


def _cpu_load_command(native_run: Path, config: Path, directory: Path) -> list[str]:
    """Return the CPU-load launcher command around one native run.

    Parameters
    ----------
    native_run
        Production controller and RTL plant executable.
    config
        Run configuration.
    directory
        Exclusive allocation for the journal, the workspace and the native outputs.

    Returns
    -------
    list[str]
        Launcher command.
    """
    return [
        sys.executable,
        str(REPOSITORY_ROOT / "tools/linux_load.py"),
        "--profile",
        "cpu",
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--journal",
        str(directory / "load.json"),
        "--workspace",
        str(directory / "worker"),
        "--",
        str(native_run.resolve()),
        str(config),
        str(directory / "events.bin"),
        str(directory / "raw.csv"),
    ]


def _readiness_frame(violation: str, worker: int) -> tuple[bytes, str]:
    """Return the readiness bytes of one violation and the expected refusal.

    Parameters
    ----------
    violation
        Pipe framing or field-type requirement to violate.
    worker
        Actual worker process ID.

    Returns
    -------
    tuple[bytes, str]
        Bytes to write to the worker's readiness pipe, and the refusal text.
    """
    frame = json.dumps({"ready": True, "pid": worker}).encode()
    fixed = {
        "partial": (frame[:1], "timed out"),
        "oversized": (b" " * MAX_READINESS_BYTES + b"\n", "frame limit"),
        "numeric_ready": (
            (json.dumps({"ready": 1, "pid": worker}) + "\n").encode(),
            "Boolean ready",
        ),
        "float_pid": (
            (json.dumps({"ready": True, "pid": float(worker)}) + "\n").encode(),
            "positive integer",
        ),
        "eof": (frame, "readiness ended"),
    }
    if violation in fixed:
        return fixed[violation]
    if violation in {"duplicate_ready", "duplicate_pid"}:
        shadow = b'"ready":false,' if violation == "duplicate_ready" else b'"pid":0,'
        return frame.replace(b"{", b"{" + shadow, 1) + b"\n", "duplicate JSON key"
    return frame + b"\n{}\n", "worker readiness: invalid JSON"
