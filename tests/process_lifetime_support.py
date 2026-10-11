# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded cleanup of actual owned test processes

"""Close test process lifetimes through retained kernel identities."""

from __future__ import annotations

import os
import signal
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess


def stop_pidfd(descriptor: int) -> None:
    """Stop an exclusively owned process even if its numeric PID was released.

    Parameters
    ----------
    descriptor
        Retained pidfd acquired from the actual owned process while unreaped.

    Raises
    ------
    OSError
        If the retained descriptor cannot be signalled, apart from an exited process.
    """
    with suppress(ProcessLookupError):
        signal.pidfd_send_signal(descriptor, signal.SIGKILL)


def retain_process(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> int:
    """Retain the actual child identity or finish it if descriptor acquisition fails.

    Parameters
    ----------
    process
        Actual unreaped process created by this owner.

    Returns
    -------
    int
        Exclusively owned pidfd for the supplied child.

    Raises
    ------
    OSError
        If the kernel descriptor cannot be acquired, after ending the child.
    subprocess.TimeoutExpired
        If failure cleanup exceeds the existing five-second wait limit.
    """
    try:
        return os.pidfd_open(process.pid)
    except OSError:
        process.kill()
        process.wait(timeout=5)
        raise


def finish_process(
    process: subprocess.Popen[bytes] | subprocess.Popen[str], descriptor: int
) -> None:
    """End and reap the owned process within five seconds and release its pidfd.

    Parameters
    ----------
    process
        Actual process handle whose retained kernel identity is supplied.
    descriptor
        Exclusively owned pidfd for this process, closed even on a wait failure.

    Raises
    ------
    OSError
        If signalling or releasing the actual descriptor fails.
    subprocess.TimeoutExpired
        If the actual process cannot be reaped within the existing five-second bound.
    """
    try:
        stop_pidfd(descriptor)
        process.wait(timeout=5)
    finally:
        os.close(descriptor)
