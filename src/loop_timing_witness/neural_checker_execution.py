# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual isolated checker invocation

"""Execute only the admitted source checker with a consumer-selected verified runtime."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .manifest_io import parse_json_object

if TYPE_CHECKING:
    from .neural_checker_installation import NeuralCheckerInstallation

_FILE_LIMIT = 1048576
_TRACE_LIMIT = 8 * _FILE_LIMIT
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
        "TMPDIR": str(directory),
    }


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
    trace_path = directory / "checker-open.log"
    command = (
        str(installation.interpreter.path),
        "-X",
        f"pycache_prefix={directory / 'bytecode'}",
        "-I",
        "-B",
        "-S",
        "-c",
        _LIMIT_BOOTSTRAP,
        str(installation.tracer.path),
        "--kill-on-exit",
        "-f",
        "-qq",
        "-xx",
        "-yy",
        "-s",
        "8192",
        "-e",
        "trace=openat,openat2,execve",
        "-o",
        str(trace_path),
        str(installation.interpreter.path),
        "-X",
        f"pycache_prefix={directory / 'bytecode'}",
        "-I",
        "-B",
        "-S",
        "-c",
        _BOOTSTRAP,
        str(Path(__file__).resolve().parents[1]),
        str(script),
        operation,
        *(str(path) for path in installation.import_roots),
    )
    started = time.time_ns()
    monotonic = time.monotonic_ns()
    interrupted = False
    with (
        (directory / "checker.stdout").open("wb") as stdout,
        (directory / "checker.stderr").open("wb") as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=directory,
            env=checker_environment(directory),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            start_new_session=True,
        )
        try:
            process.wait(timeout=deadline_seconds)
        except subprocess.TimeoutExpired:
            interrupted = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    observation_path = directory / "checker-observation.json"
    observation = None
    if observation_path.is_file() and observation_path.stat().st_size <= _FILE_LIMIT:
        observation = parse_json_object(observation_path.read_bytes(), "actual checker observation")
    return CheckerInvocation(
        command,
        process.returncode,
        started,
        time.time_ns(),
        time.monotonic_ns() - monotonic,
        (directory / "checker.stdout").read_bytes(),
        (directory / "checker.stderr").read_bytes(),
        trace_path.read_bytes() if trace_path.is_file() else b"",
        observation,
        interrupted,
    )
