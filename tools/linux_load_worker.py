# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual owned Linux stress worker

"""Perform bounded chunks of actual host work until the owner's control pipe closes."""

from __future__ import annotations

import argparse
import json
import os
import platform
import select
import socket
import sys
import time
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from linux_load_config import PROFILES, LoadConfiguration

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import BinaryIO


class _Workload:
    """Own the resources and counters of one selected host workload."""

    def __init__(
        self, configuration: LoadConfiguration, workspace: Path, resources: ExitStack
    ) -> None:
        """Allocate only the selected workload resources in the owner's stack.

        Parameters
        ----------
        configuration
            Validated workload profile and bounded buffer size.
        workspace
            Exclusive directory for the storage profile's retained working file.
        resources
            Owner's stack closing all sockets and working files after collection.
        """
        self.profile = configuration.profile
        size = configuration.working_set_bytes
        self.counters = dict.fromkeys(
            (
                "chunks",
                "arithmetic_operations",
                "memory_touches",
                "datagrams",
                "bytes_sent",
                "bytes_received",
                "bytes_written",
                "bytes_read",
                "fsyncs",
                "idle_waits",
            ),
            0,
        )
        self.checksum = 0
        self.memory = bytearray(size if self.profile == "memory" else 0)
        self.payload = (
            (bytes(range(256)) * ((size + 255) // 256))[:size]
            if self.profile in {"network", "storage"}
            else b""
        )
        self.operation: Callable[[], None]
        if self.profile == "network":
            receiver = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sender = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(1)
            sender.bind(("127.0.0.1", 0))
            self.operation = partial(self._network, receiver, sender)
        elif self.profile == "storage":
            storage = resources.enter_context((workspace / "storage.bin").open("x+b"))
            self.operation = partial(self._storage, storage)
        else:
            self.operation = {"cpu": self._cpu, "memory": self._memory, "idle": self._idle}[
                self.profile
            ]

    def _cpu(self) -> None:
        """Perform one bounded integer arithmetic chunk."""
        for value in range(4096):
            self.checksum = (self.checksum * 1664525 + value + 1013904223) & 0xFFFFFFFF
        self.counters["arithmetic_operations"] += 4096

    def _memory(self) -> None:
        """Read and modify one byte per explicit 64-byte stride."""
        for index in range(0, len(self.memory), 64):
            self.memory[index] = (self.memory[index] + 1) & 255
            self.checksum = (self.checksum + self.memory[index]) & 0xFFFFFFFF
            self.counters["memory_touches"] += 1

    def _network(self, receiver: socket.socket, sender: socket.socket) -> None:
        """Send and verify one datagram through owned loopback sockets.

        Parameters
        ----------
        receiver
            Open bound socket, closed by the collection resource stack.
        sender
            Open bound transmitting socket from the same resource stack.
        """
        sent = sender.sendto(self.payload, receiver.getsockname())
        received, address = receiver.recvfrom(len(self.payload) + 1)
        if sent != len(self.payload) or received != self.payload or address != sender.getsockname():
            message = "loopback load datagram differs from transmitted data"
            raise ValueError(message)
        self.counters["datagrams"] += 1
        self.counters["bytes_sent"] += sent
        self.counters["bytes_received"] += len(received)
        self.checksum = (self.checksum + sum(received)) & 0xFFFFFFFF

    def _storage(self, storage: BinaryIO) -> None:
        """Write, sync and verify the bounded owned working file.

        Parameters
        ----------
        storage
            Open exclusive working file, closed by the collection resource stack.
        """
        storage.seek(0)
        written = storage.write(self.payload)
        storage.flush()
        os.fsync(storage.fileno())
        storage.seek(0)
        received = storage.read()
        if written != len(self.payload) or received != self.payload:
            message = "storage load readback differs from written data"
            raise ValueError(message)
        self.counters["bytes_written"] += written
        self.counters["bytes_read"] += len(received)
        self.counters["fsyncs"] += 1
        self.checksum = (self.checksum + sum(received)) & 0xFFFFFFFF

    def _idle(self) -> None:
        """Wait on the owner's pipe without generating busy work."""
        select.select([sys.stdin], [], [], 0.01)
        self.counters["idle_waits"] += 1

    def run(self) -> None:
        """Report readiness after actual work and continue until owner pipe closure."""
        ready = False
        while not ready or not select.select([sys.stdin], [], [], 0)[0]:
            self.operation()
            self.counters["chunks"] += 1
            if not ready:
                print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
                ready = True


def _apply_policy(cpu: int) -> dict[str, int | list[int]]:
    """Apply and verify normal scheduling and the requested worker CPU.

    Parameters
    ----------
    cpu
        Explicit CPU already validated against the worker's inherited allowed set.

    Returns
    -------
    dict of str to int or list of int
        Actual kernel scheduler, priority, affinity and nice readback.
    """
    os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
    os.sched_setaffinity(0, {cpu})
    policy: dict[str, int | list[int]] = {
        "scheduler": os.sched_getscheduler(0),
        "priority": os.sched_getparam(0).sched_priority,
        "affinity_cpus": sorted(os.sched_getaffinity(0)),
        "nice": os.getpriority(os.PRIO_PROCESS, 0),
    }
    if (
        policy["scheduler"] != os.SCHED_OTHER
        or policy["priority"] != 0
        or policy["affinity_cpus"] != [cpu]
    ):
        message = "load worker policy differs from request"
        raise ValueError(message)
    return policy


def collect(configuration: LoadConfiguration, workspace: Path) -> None:
    """Retain actual operations and policy from the owned worker span.

    Parameters
    ----------
    configuration
        Explicit profile, allowed CPU and buffer limit.
    workspace
        Owner-created private directory for retained working data and receipt.

    Raises
    ------
    OSError
        If scheduling, socket, file or operation access fails.
    ValueError
        If policy readback or transferred data differs from the request.
    """
    configuration.validate()
    policy = _apply_policy(configuration.cpu)
    started = time.monotonic_ns()
    with ExitStack() as resources:
        workload = _Workload(configuration, workspace, resources)
        workload.run()
    profile = configuration.profile
    receipt = {
        "schema": "loop-timing-witness.host-load.v1",
        "profile": profile,
        "requested_cpu": configuration.cpu,
        "working_set_bytes": configuration.working_set_bytes,
        "worker_pid": os.getpid(),
        "python_version": platform.python_version(),
        "started_ns": started,
        "finished_ns": time.monotonic_ns(),
        "policy": policy,
        "counters": workload.counters,
        "checksum": workload.checksum,
        "network_scope": "loopback_udp" if profile == "network" else None,
        "storage_scope": "owned_file_fsync" if profile == "storage" else None,
    }
    with (workspace / "worker.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Run the owned worker through its control-pipe command interface.

    Parameters
    ----------
    argv
        Explicit profile, CPU, working set and workspace arguments.

    Returns
    -------
    int
        Zero after complete collection, one after a retained failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("cpu", type=int)
    parser.add_argument("working_set_bytes", type=int)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args(argv)
    try:
        collect(LoadConfiguration(args.profile, args.cpu, args.working_set_bytes), args.workspace)
    except (OSError, ValueError) as exc:
        print(f"Linux load worker: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
