# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — owned process observation and cleanup

"""Observe, stop and reap only child groups owned by the native load launcher."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress


def _signal_group(pid: int, signal_number: int) -> None:
    """Signal an owned group while its unreaped leader retains the numeric identity.

    Parameters
    ----------
    pid
        PID of the owned, unreaped session and process group leader.
    signal_number
        Requested Linux signal; concurrent exit is tolerated.
    """
    with suppress(ProcessLookupError):
        os.killpg(pid, signal_number)


def _exit_status(process: subprocess.Popen[bytes]) -> int | None:
    """Observe an owned child without releasing its PID or process group identity.

    Parameters
    ----------
    process
        Actual owned child handle whose exit has not yet been reaped.

    Returns
    -------
    int or None
        Exit code or negative terminating signal, or None while still running.
    """
    status = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if status is None:
        return None
    return status.si_status if status.si_code == os.CLD_EXITED else -status.si_status


def _wait_exit(process: subprocess.Popen[bytes], timeout: float) -> int:
    """Wait for an owned exit while retaining the unreaped group leader.

    Parameters
    ----------
    process
        Owned child whose PID remains reserved until the caller reaps it.
    timeout
        Caller-validated maximum wait in seconds.

    Returns
    -------
    int
        Actual exit code or negative terminating signal.

    Raises
    ------
    subprocess.TimeoutExpired
        If the owned child does not exit before the deadline.
    """
    deadline = time.monotonic() + timeout
    while (status := _exit_status(process)) is None:
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(process.args, timeout)
        time.sleep(0.01)
    return status


def _reap(process: subprocess.Popen[bytes]) -> None:
    """Stop the owned group before reaping, retaining identity throughout cleanup.

    Parameters
    ----------
    process
        Unreaped child and group leader created by the owning launcher.

    Raises
    ------
    subprocess.TimeoutExpired
        If the child still cannot be reaped after the final kill and bounded wait.
    """
    try:
        _signal_group(process.pid, signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            _wait_exit(process, 2)
    finally:
        _signal_group(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
