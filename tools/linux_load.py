# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native execution with owned Linux host load

"""Run a native controller while one measured, owned Linux load worker is active."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from linux_load_channels import WorkerChannels, worker_channels
from linux_load_config import PROFILES, LoadConfiguration
from linux_load_process import _exit_status, _reap, _wait_exit
from linux_load_readiness import READINESS_TIMEOUT_SECONDS, read_ready_pid

from manifest_io import load_json_object

MAX_TIMEOUT_SECONDS = 3600


@dataclass(frozen=True)
class LoadExecution:
    """Exclusive output paths and lifetime for one native controller invocation.

    Parameters
    ----------
    journal
        New completion receipt path.
    workspace
        New private worker resource directory.
    timeout
        Native lifetime in seconds, between one and 3600.
    worker_path
        Optional frozen worker source for a captured run.
    """

    journal: Path
    workspace: Path
    timeout: float = 120
    worker_path: Path | None = None


def _await_ready(worker: subprocess.Popen[bytes], channels: WorkerChannels) -> None:
    """Require bounded, typed readiness before launching the native controller.

    Parameters
    ----------
    worker
        Actual owned child whose PID must match the complete readiness frame.
    channels
        Owned pipe endpoints kept open throughout worker admission and cleanup.
    """
    try:
        pid = read_ready_pid(channels.readiness)
    except TimeoutError:
        raise subprocess.TimeoutExpired(worker.args, READINESS_TIMEOUT_SECONDS) from None
    if pid != worker.pid:
        message = "load worker readiness differs from owned process"
        raise ValueError(message)


def _await_native(
    native: subprocess.Popen[bytes], worker: subprocess.Popen[bytes], timeout: float
) -> int:
    """Bound native execution and refuse a prematurely exited workload.

    Parameters
    ----------
    native
        Owned controller child whose exit is observed without reaping.
    worker
        Owned workload child required to remain present during native execution.
    timeout
        Validated maximum native lifetime in seconds.

    Returns
    -------
    int
        Actual native exit code or negative terminating signal.
    """
    deadline = time.monotonic() + timeout
    while (status := _exit_status(native)) is None:
        if _exit_status(worker) is not None:
            message = "load worker exited during native execution"
            raise subprocess.SubprocessError(message)
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(native.args, timeout)
        time.sleep(0.01)
    return status


def _write_receipt(
    worker: subprocess.Popen[bytes],
    native: subprocess.Popen[bytes],
    execution: LoadExecution,
    completion: tuple[int, int, int],
    channels: WorkerChannels,
) -> None:
    """Bind the actual native interval to the completed owned worker receipt.

    Parameters
    ----------
    worker
        Owned workload producer whose actual exit and PID are verified.
    native
        Unreaped native child whose identity is retained in the final receipt.
    execution
        Exclusive receipt and actual worker workspace paths.
    completion
        Actual native monotonic start, finish and exit status.
    channels
        Owned control writer closed to finish collection before reading its receipt.
    """
    channels.stop()
    worker_returncode = _wait_exit(worker, 10)
    if worker_returncode:
        raise subprocess.CalledProcessError(worker_returncode, worker.args)
    receipt = load_json_object(execution.workspace / "worker.json")
    started, finished, returncode = completion
    if (
        receipt["worker_pid"] != worker.pid
        or not receipt["started_ns"] <= started <= finished <= receipt["finished_ns"]
    ):
        message = "load collection does not cover native execution"
        raise ValueError(message)
    receipt.update(
        native_pid=native.pid,
        native_started_ns=started,
        native_finished_ns=finished,
        native_returncode=returncode,
    )
    with execution.journal.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


def execute_with_load(
    command: list[str], configuration: LoadConfiguration, execution: LoadExecution, stdout: BinaryIO
) -> subprocess.CompletedProcess[bytes]:
    """Run an operator-selected native executable with actual measured host load.

    Parameters
    ----------
    command
        Absolute native executable and arguments, executed without a shell.
    configuration
        Explicit profile, CPU and resource bounds.
    execution
        Exclusive receipt/workspace paths and bounded native lifetime.
    stdout
        Native stdout and stderr destination.

    Returns
    -------
    subprocess.CompletedProcess of bytes
        Actual native return code, including native failures.

    Raises
    ------
    OSError
        If exclusive resources, executable or receipt cannot be accessed.
    ValueError
        If configuration, readiness or receipt time brackets are invalid.
    subprocess.SubprocessError
        If execution exceeds its lifetime or the worker exits prematurely.
    """
    configuration.validate()
    if not command or not 1 <= execution.timeout <= MAX_TIMEOUT_SECONDS:
        message = "native command and bounded load timeout are required"
        raise ValueError(message)
    program = Path(command[0])
    if not program.is_absolute() or not program.is_file() or not os.access(program, os.X_OK):
        message = "native executable must be an executable absolute file path"
        raise ValueError(message)
    if execution.journal.exists() or execution.journal.is_symlink():
        message = "load journal already exists"
        raise FileExistsError(message)
    execution.workspace.mkdir(mode=0o700)
    source = execution.worker_path or Path(__file__).with_name("linux_load_worker.py")
    with (
        (execution.workspace / "worker.log").open("xb") as log,
        worker_channels() as channels,
        ExitStack() as processes,
    ):
        worker = subprocess.Popen(
            [
                sys.executable,
                str(source),
                configuration.profile,
                str(configuration.cpu),
                str(configuration.working_set_bytes),
                str(execution.workspace.resolve()),
            ],
            stdin=channels.child_input,
            stdout=channels.child_output,
            stderr=log,
            start_new_session=True,
        )
        processes.callback(_reap, worker)
        channels.release_child_ends()
        _await_ready(worker, channels)
        started = time.monotonic_ns()
        native = subprocess.Popen(
            command, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True
        )
        processes.callback(_reap, native)
        returncode = _await_native(native, worker, execution.timeout)
        finished = time.monotonic_ns()
        _write_receipt(worker, native, execution, (started, finished, returncode), channels)
        return subprocess.CompletedProcess(command, returncode)


def main(argv: list[str] | None = None) -> int:
    """Launch a native command with a measured host profile and exclusive receipt.

    Parameters
    ----------
    argv
        Load options followed by the native command after ``--``.

    Returns
    -------
    int
        Native return code, or one for a retained load/launch failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=PROFILES)
    parser.add_argument("--cpu", required=True, type=int)
    parser.add_argument("--working-set-bytes", default=4096, type=int)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--timeout", default=120, type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result = execute_with_load(
            command,
            LoadConfiguration(args.profile, args.cpu, args.working_set_bytes),
            LoadExecution(args.journal, args.workspace, args.timeout),
            sys.stdout.buffer,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Linux load: FAIL: {exc}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
