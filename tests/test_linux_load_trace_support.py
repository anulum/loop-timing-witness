# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — kernel lifetime ownership of real traced children

"""Verify cleanup when a tracer dies before its child has been observed."""

from __future__ import annotations

import os
import select
import signal
import sys
from contextlib import suppress
from pathlib import Path

from linux_load_trace_support import trace_command


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
        assert select.select([trace.process.stdout], [], [], 5)[0]
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
            assert select.select([descriptor], [], [], 5)[0]
            assert trace.process.wait(timeout=5) == -signal.SIGKILL
        finally:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            os.close(descriptor)
