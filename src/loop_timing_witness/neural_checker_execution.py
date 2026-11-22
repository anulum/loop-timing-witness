# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual isolated checker invocation

"""Execute only the admitted source checker with a consumer-selected verified runtime."""

from __future__ import annotations

import contextlib
import os
import signal
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .neural_event_stream import NeuralCaptureRefusalError
from .neural_json_shapes import REFERENCE_FIELDS, records, texts, typed
from .strict_json import JsonInputRefusalError, parse_json_object

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .neural_checker_installation import NeuralCheckerInstallation

_FILE_LIMIT = 1048576
_TRACE_LIMIT = 8 * _FILE_LIMIT
_TRACE_NAME = "checker-open.log"
_WALL_SECONDS = 45
_LIMIT_BOOTSTRAP = (
    "import os,resource,sys; "
    "resource.setrlimit(resource.RLIMIT_AS,(805306368,805306368)); "
    "resource.setrlimit(resource.RLIMIT_CORE,(0,0)); "
    "resource.setrlimit(resource.RLIMIT_CPU,(30,30)); "
    "resource.setrlimit(resource.RLIMIT_FSIZE,(8388608,8388608)); "
    "os.execv(sys.argv[1],sys.argv[1:])"
)
_BOOTSTRAP = (
    "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
    "runpy.run_module('loop_timing_witness.neural_checker_worker',run_name='__main__')"
)
_ISOLATED = ("-I", "-B", "-S", "-c")
_TRACER_OPTIONS = (
    "--kill-on-exit",
    "-f",
    "-qq",
    "-xx",
    "-yy",
    "-s",
    "8192",
    "-e",
    "trace=open,openat,openat2,creat,execve,execveat",
    "-o",
)


_I32 = 2**31
_OBSERVATION_FIELDS = frozenset(
    {
        "schema_id",
        "operation",
        "actual_argv",
        "native_returncode",
        "phase",
        "started_ns",
        "completed_ns",
        "elapsed_ns",
        "modules",
        "files",
    }
)


def bounded_output(path: Path, limit: int) -> bytes:
    """Read one checker output as a bounded regular file without following a link.

    Parameters
    ----------
    path
        Output inside a consumer-owned directory.
    limit
        Largest admitted byte length.

    Returns
    -------
    bytes
        Complete output bytes.

    Raises
    ------
    NeuralCaptureRefusalError
        If the output is absent, a link, nonregular, unreadable or excessive.
    """
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                message = "Actual checker output must be a regular file."
                raise NeuralCaptureRefusalError(message)
            raw = stream.read(limit + 1)
    except OSError as exc:
        message = "Actual checker output is unavailable."
        raise NeuralCaptureRefusalError(message) from exc
    if len(raw) > limit:
        message = "Actual checker output exceeds its allocation."
        raise NeuralCaptureRefusalError(message)
    return raw


def _observation_closed(observation: dict[str, Any]) -> bool:
    """Tell whether a worker observation has the complete closed form.

    Parameters
    ----------
    observation
        Decoded observation.

    Returns
    -------
    bool
        Whether every field is present and typed, and nothing else is declared.
    """
    return (
        set(observation) == _OBSERVATION_FIELDS
        and all(typed(observation[name], str) for name in ("schema_id", "operation", "phase"))
        and texts(observation["actual_argv"])
        and type(observation["native_returncode"]) is int
        and -_I32 <= observation["native_returncode"] < _I32
        and all(
            typed(observation[name], int) for name in ("started_ns", "completed_ns", "elapsed_ns")
        )
        and records(observation["modules"], {"name": str, "path": str})
        and records(observation["files"], REFERENCE_FIELDS)
    )


def read_observation(path: Path) -> dict[str, Any] | None:
    """Read the worker observation the checker left, if it left one.

    Parameters
    ----------
    path
        ``checker-observation.json`` in the owned operation directory.

    Returns
    -------
    dict[str, Any] or None
        Closed observation, or ``None`` when no file exists.

    Raises
    ------
    NeuralCaptureRefusalError
        If the file is a link, nonregular, excessive, malformed or not closed.
    """
    if not path.exists():
        return None
    raw = bounded_output(path, _FILE_LIMIT)
    try:
        observation = parse_json_object(raw, "actual checker observation")
    except JsonInputRefusalError as exc:
        message = "Invalid original actual checker observation."
        raise NeuralCaptureRefusalError(message) from exc
    if not _observation_closed(observation):
        message = "Invalid original actual checker observation."
        raise NeuralCaptureRefusalError(message)
    return observation


@dataclass(frozen=True, slots=True)
class CheckerInvocation:
    """Actual finite child-process observations, without inferred successful execution.

    Attributes
    ----------
    command, returncode, started_ns, completed_ns, elapsed_ns
        Actual parent command, native status and measured execution times.
    stdout, stderr, trace, observation
        Complete finite original logs, process trace and worker observation.
    interrupted
        Whether the deadline required stopping and reaping the entire owned group.
    """

    command: tuple[str, ...]
    returncode: int
    started_ns: int
    completed_ns: int
    elapsed_ns: int
    stdout: bytes
    stderr: bytes
    trace: bytes
    observation: dict[str, Any] | None
    interrupted: bool


def exact_text(path: Path) -> str:
    """Return a path as exact UTF-8 text for a recorded command.

    Parameters
    ----------
    path
        Host path placed in a command or environment.

    Returns
    -------
    str
        The path text.

    Raises
    ------
    NeuralCaptureRefusalError
        If the path bytes are not UTF-8, so a report could not record them exactly.
    """
    text = str(path)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        message = "Checker path requires exact UTF-8."
        raise NeuralCaptureRefusalError(message) from exc
    return text


def checker_environment(directory: Path) -> dict[str, str]:
    """Construct the closed checker environment without inherited executable selectors.

    Parameters
    ----------
    directory
        Owned private working directory of this actual invocation.

    Returns
    -------
    dict[str, str]
        Fixed locale, timezone, thread bounds and within-job temporary directory.
    """
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "TMPDIR": exact_text(directory),
    }


@dataclass(frozen=True, slots=True)
class GroupRun:
    """Measured native completion of one owned process group.

    Attributes
    ----------
    returncode, started_ns, completed_ns, elapsed_ns
        Native status, wall-clock start and completion, and monotonic duration.
    interrupted
        Whether the deadline required stopping and reaping the entire owned group.
    """

    returncode: int
    started_ns: int
    completed_ns: int
    elapsed_ns: int
    interrupted: bool


def _wait_or_reap(process: subprocess.Popen[bytes], deadline_seconds: float) -> bool:
    """Wait for the child, killing and reaping its whole group if it must stop.

    Parameters
    ----------
    process
        Child started as the leader of its own session.
    deadline_seconds
        Wall-clock limit of the wait.

    Returns
    -------
    bool
        Whether the deadline stopped the group.

    Raises
    ------
    BaseException
        Whatever interrupted the waiting parent, re-raised after the group is reaped.
    """
    try:
        process.wait(timeout=deadline_seconds)
    except subprocess.TimeoutExpired:
        _stop_group(process.pid)
        process.wait()
        return True
    except BaseException:
        _stop_group(process.pid)
        process.wait()
        raise
    # A child the leader left running, such as a launcher's background process, is stopped
    # with the group too, so nothing of the invocation outlives it.
    _stop_group(process.pid)
    return False


def _stop_group(group: int) -> None:
    """Kill every process left in one owned session group; an empty group is no failure.

    Parameters
    ----------
    group
        Process group of the leader started in its own session.
    """
    with contextlib.suppress(ProcessLookupError):
        os.killpg(group, signal.SIGKILL)


def run_owned_group(
    command: Sequence[str],
    directory: Path,
    environment: dict[str, str],
    outputs: tuple[Path, Path],
    deadline_seconds: float,
) -> GroupRun:
    """Run one command as its own session and reap the whole group when it must stop.

    Parameters
    ----------
    command
        Complete argument vector; no shell interprets it.
    directory
        Owned working directory of the child.
    environment
        Complete closed child environment; nothing is inherited.
    outputs
        Files receiving the child's standard output and standard error.
    deadline_seconds
        Wall-clock limit after which the whole group is killed and reaped.

    Returns
    -------
    GroupRun
        Native status and measured times. A deadline is a known interruption and
        never restarts the child or fabricates success.
    """
    started = time.time_ns()
    monotonic = time.monotonic_ns()
    with outputs[0].open("wb") as stdout, outputs[1].open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=directory,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            start_new_session=True,
        )
        interrupted = _wait_or_reap(process, deadline_seconds)
    completed = time.time_ns()
    elapsed = time.monotonic_ns() - monotonic
    return GroupRun(process.returncode, started, completed, elapsed, interrupted)


def _isolated_python(
    installation: NeuralCheckerInstallation, directory: Path, bootstrap: str
) -> tuple[str, ...]:
    """Return the isolated interpreter prefix that runs one fixed bootstrap text.

    Parameters
    ----------
    installation
        Verified runtime whose interpreter runs the bootstrap.
    directory
        Owned invocation directory holding the bytecode cache.
    bootstrap
        Fixed program text passed with ``-c``.

    Returns
    -------
    tuple[str, ...]
        Interpreter, cache prefix, isolation flags and the bootstrap.
    """
    return (
        exact_text(installation.interpreter.path),
        "-X",
        f"pycache_prefix={exact_text(directory / 'bytecode')}",
        *_ISOLATED,
        bootstrap,
    )


def checker_command(
    installation: NeuralCheckerInstallation, script: Path, operation: str, directory: Path
) -> tuple[str, ...]:
    """Return the fixed traced command of one source-checker operation.

    Parameters
    ----------
    installation
        Consumer registry runtime already verified against its full contract.
    script
        Within-job copy of the exact byte-bound source-owned entry point.
    operation
        Fixed ``generate`` or ``check`` operation selected by the full verifier.
    directory
        Owned invocation directory, never a receipt-supplied working directory.

    Returns
    -------
    tuple[str, ...]
        Resource-limited tracer launch of the isolated worker bootstrap.
    """
    return (
        *_isolated_python(installation, directory, _LIMIT_BOOTSTRAP),
        exact_text(installation.tracer.path),
        *_TRACER_OPTIONS,
        exact_text(directory / _TRACE_NAME),
        *_isolated_python(installation, directory, _BOOTSTRAP),
        exact_text(Path(__file__).resolve().parents[1]),
        exact_text(script),
        operation,
        *(exact_text(path) for path in installation.import_roots),
    )


def invoke_source_checker(
    installation: NeuralCheckerInstallation,
    script: Path,
    operation: str,
    directory: Path,
    *,
    deadline_seconds: float = _WALL_SECONDS,
) -> CheckerInvocation:
    """Run one fixed source operation and retain every native completion observation.

    Parameters
    ----------
    installation
        Consumer registry runtime already verified against its full contract.
    script
        Within-job copy of the exact byte-bound source-owned entry point.
    operation
        Fixed ``generate`` or ``check`` operation selected by the full verifier.
    directory
        Owned invocation directory, never a receipt-supplied working directory.
    deadline_seconds
        Wall-clock limit of the reviewed execution contract.

    Returns
    -------
    CheckerInvocation
        Complete original logs and measured native status. A timeout is a known
        interrupted execution and never restarts the producer or fabricates success.
    """
    command = checker_command(installation, script, operation, directory)
    outputs = (directory / "checker.stdout", directory / "checker.stderr")
    run = run_owned_group(
        command, directory, checker_environment(directory), outputs, deadline_seconds
    )
    observation = read_observation(directory / "checker-observation.json")
    trace_path = directory / _TRACE_NAME
    return CheckerInvocation(
        command,
        run.returncode,
        run.started_ns,
        run.completed_ns,
        run.elapsed_ns,
        bounded_output(outputs[0], _FILE_LIMIT),
        bounded_output(outputs[1], _FILE_LIMIT),
        bounded_output(trace_path, _TRACE_LIMIT) if trace_path.exists() else b"",
        observation,
        run.interrupted,
    )
