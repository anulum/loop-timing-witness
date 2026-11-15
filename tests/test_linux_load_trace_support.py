# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — kernel lifetime ownership of real traced children

"""Verify tracer cleanup, child pidfd opening and the reaping of a tracer that stops responding."""

from __future__ import annotations

import errno
import os
import resource
import select
import signal
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import linux_load_trace_support
import pytest
from linux_load_trace_support import open_child, trace_command

from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Callable


def test_tracer_exit_ends_unobserved_owned_child(tmp_path: Path) -> None:
    """End the actual unknown tracee and close its inherited pipes on tracer death.

    Parameters
    ----------
    tmp_path
        Exclusive actual syscall log and controller workspace.
    """
    with trace_command(
        [sys.executable, "-c", "import os,time; print(os.getpid(),flush=True); time.sleep(30)"],
        "sched_getscheduler:delay_enter=1us:when=1",
        tmp_path / "unobserved-child.strace",
    ) as trace:
        assert trace.process.stdout is not None
        assert select.select([trace.process.stdout], [], [], scaled(5))[0]
        child = int(trace.process.stdout.readline())
        assert child in map(
            int,
            Path(f"/proc/{trace.process.pid}/task/{trace.process.pid}/children")
            .read_text()
            .split(),
        )
        descriptor = os.pidfd_open(child)
        try:
            assert list(trace.descriptors) == [trace.process.pid]
            assert not select.select([descriptor], [], [], 0)[0]
            signal.pidfd_send_signal(trace.descriptors[trace.process.pid], signal.SIGKILL)
            assert select.select([descriptor], [], [], scaled(5))[0]
            assert trace.process.wait(timeout=scaled(5)) == -signal.SIGKILL
        finally:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            os.close(descriptor)


def test_open_child_answers_none_for_a_thread_or_an_exited_child() -> None:
    """Open a live process; answer ``None`` for a non-leader thread and an unused pid."""
    started = threading.Event()
    stop = threading.Event()
    native: list[int] = []

    def worker() -> None:
        native.append(threading.get_native_id())
        started.set()
        stop.wait(scaled(5))

    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert started.wait(scaled(5))
        with pytest.raises(OSError, match=r"Invalid argument|No such file") as refusal:
            os.pidfd_open(native[0])
        assert refusal.value.errno in {errno.EINVAL, errno.ENOENT}
        assert open_child(native[0]) is None
    finally:
        stop.set()
        thread.join()
    # No process can hold pid_max itself, so the kernel answers ESRCH as for an exited child.
    unused = int(Path("/proc/sys/kernel/pid_max").read_text())
    assert open_child(unused) is None
    descriptor = open_child(os.getpid())
    assert descriptor is not None
    os.close(descriptor)


def test_open_child_keeps_other_kernel_refusals() -> None:
    """Let a refusal other than a vanished child or a thread through, here EMFILE."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    probe = os.dup(0)
    os.close(probe)
    resource.setrlimit(resource.RLIMIT_NOFILE, (probe, hard))
    try:
        with pytest.raises(OSError, match="Too many open files") as refusal:
            open_child(os.getpid())
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    assert refusal.value.errno == errno.EMFILE


def test_close_reaps_the_tracer_when_observation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kill and reap the actual tracer when observing its children fails, and keep the error.

    Parameters
    ----------
    tmp_path
        Exclusive actual syscall log.
    monkeypatch
        Makes the child pidfd opening fail as an unexpected kernel answer would.
    """

    def refuse(_pid: int) -> int | None:
        raise OSError(errno.EPERM, "Operation not permitted")

    tracers: list[subprocess.Popen[str]] = []
    with pytest.raises(OSError, match="Operation not permitted"):
        trace_with_failing_observation(
            tmp_path / "failed-observation.strace", tracers, monkeypatch, refuse
        )
    assert tracers[0].returncode == -signal.SIGKILL


def trace_with_failing_observation(
    log: Path,
    tracers: list[subprocess.Popen[str]],
    monkeypatch: pytest.MonkeyPatch,
    refuse: Callable[[int], int | None],
) -> None:
    """Trace a sleeping child and make the closing observation open no pidfd.

    Parameters
    ----------
    log
        Exclusive actual syscall log.
    tracers
        Receives the actual tracer process for the caller's checks.
    monkeypatch
        Installs ``refuse`` until the test ends.
    refuse
        Replacement child pidfd opener, installed once the tracer lists its child.
    """
    with trace_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        "sched_getscheduler:delay_enter=1us:when=1",
        log,
    ) as trace:
        tracers.append(trace.process)
        children = Path(f"/proc/{trace.process.pid}/task/{trace.process.pid}/children")
        assert wait_for_children(children)
        monkeypatch.setattr(linux_load_trace_support, "open_child", refuse)


def wait_for_children(children: Path) -> bool:
    """Wait until a process lists at least one child.

    Parameters
    ----------
    children
        The process's ``children`` file.

    Returns
    -------
    bool
        Whether a child appeared within the scaled bound.
    """
    deadline = time.monotonic() + scaled(5)
    while time.monotonic() < deadline:
        if children.read_text().split():
            return True
        time.sleep(0.01)
    return False
