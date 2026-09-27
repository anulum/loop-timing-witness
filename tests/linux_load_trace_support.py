# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded tracing of exclusively owned test processes

"""Delay real syscalls without replacing results, and own every traced test process."""

from __future__ import annotations

import os
import select
import shutil
import signal
import subprocess
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class OwnedTrace:
    """Tracer, retained syscall log and pidfds for its actual descendant tree.

    Parameters
    ----------
    process
        Owned tracer process, started in an exclusive session.
    log
        Exclusive syscall trace file.
    descriptors
        Open pidfds keyed by observed, exclusively owned process IDs.
    """

    process: subprocess.Popen[str]
    log: Path
    descriptors: dict[int, int] = field(default_factory=dict)

    def observe(self) -> None:
        """Retain pidfds for live descendants while their known parent remains live."""
        pending = list(self.descriptors)
        while pending:
            parent = pending.pop()
            descriptor = self.descriptors[parent]
            if select.select([descriptor], [], [], 0)[0]:
                continue
            children_file = Path(f"/proc/{parent}/task/{parent}/children")
            with suppress(FileNotFoundError):
                children = children_file.read_text().split()
                if select.select([descriptor], [], [], 0)[0]:
                    continue
                for child in map(int, children):
                    if child in self.descriptors:
                        continue
                    with suppress(ProcessLookupError):
                        child_descriptor = os.pidfd_open(child)
                        try:
                            status = Path(f"/proc/{child}/status").read_text()
                        except FileNotFoundError:
                            os.close(child_descriptor)
                            continue
                        parent_matches = any(
                            line.split() == ["PPid:", str(parent)] for line in status.splitlines()
                        )
                        if (
                            not parent_matches
                            or select.select([descriptor, child_descriptor], [], [], 0)[0]
                        ):
                            os.close(child_descriptor)
                            continue
                        self.descriptors[child] = child_descriptor
                        pending.append(child)

    def close(self) -> None:
        """Kill only retained owned identities and reap the tracer before closing pidfds."""
        try:
            self.observe()
            for descriptor in reversed(list(self.descriptors.values())):
                with suppress(ProcessLookupError):
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            self.process.communicate(timeout=5)
        finally:
            for descriptor in self.descriptors.values():
                os.close(descriptor)


@contextmanager
def trace_command(command: list[str], delay: str, log: Path) -> Iterator[OwnedTrace]:
    """Trace one actual command and delay only the named syscall entry.

    Parameters
    ----------
    command
        Actual production executable and argument vector, without a shell.
    delay
        Strace syscall delay expression; no result or memory substitution.
    log
        Exclusive trace destination retained by this test.

    Yields
    ------
    OwnedTrace
        Real tracer and bounded ownership of its descendants.
    """
    tracer = shutil.which("strace")
    assert tracer is not None, "strace is required for real syscall-boundary tests"
    assert not log.exists()
    process = subprocess.Popen(
        [
            tracer,
            "-f",
            "-o",
            str(log),
            "-e",
            "trace=sched_setaffinity,sched_getscheduler,exit_group",
            "-e",
            "inject=" + delay,
            *command,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    trace = OwnedTrace(process, log, {process.pid: os.pidfd_open(process.pid)})
    try:
        yield trace
    finally:
        trace.close()
