# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — wall time and resource use of one pinned child command

"""Time one child command end to end and summarise samples as the benchmark standard asks.

The wall time spans process creation to reaping, measured with ``time.perf_counter_ns``;
it includes interpreter or program start-up, input reading and report publication, which
is what a user of either command waits for. The child is pinned with ``taskset`` to one CPU
of the caller's allowed set. Pinning does not reserve the core.
"""

from __future__ import annotations

import os
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

MIN_SAMPLES: Final = 5


@dataclass(frozen=True, slots=True)
class TimedSample:
    """One reaped child: its exit status, output, wall time and resource use.

    Attributes
    ----------
    status
        Exit status; a signal ``n`` is reported as ``-n``.
    stdout
        Standard output text.
    stderr
        Standard error text.
    elapsed_ns
        Wall time from process creation to reaping.
    max_rss_kib
        Peak resident set size of the child, in KiB.
    user_seconds
        User CPU time of the child.
    system_seconds
        System CPU time of the child.
    """

    status: int
    stdout: str
    stderr: str
    elapsed_ns: int
    max_rss_kib: int
    user_seconds: float
    system_seconds: float


def run_timed(argv: list[str], cpu: int, cwd: Path, timeout: float) -> TimedSample:
    """Run one command pinned to a CPU and return its outcome and resource use.

    Parameters
    ----------
    argv
        Command and arguments.
    cpu
        CPU for ``taskset --cpu-list``.
    cwd
        Working directory, which also receives the captured output files.
    timeout
        Hang guard in seconds; the child is killed when it is exceeded.

    Returns
    -------
    TimedSample
        Status, output, wall time and the child's own resource use.
    """
    stdout_path, stderr_path = cwd / ".timed-stdout", cwd / ".timed-stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        start = time.perf_counter_ns()
        process = subprocess.Popen(
            ["taskset", "--cpu-list", str(cpu), *argv],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        guard = threading.Timer(timeout, process.kill)
        guard.start()
        _, wait_status, usage = os.wait4(process.pid, 0)
        elapsed = time.perf_counter_ns() - start
        guard.cancel()
    process.returncode = os.waitstatus_to_exitcode(wait_status)
    sample = TimedSample(
        status=process.returncode,
        stdout=stdout_path.read_text(encoding="utf-8"),
        stderr=stderr_path.read_text(encoding="utf-8"),
        elapsed_ns=elapsed,
        max_rss_kib=usage.ru_maxrss,
        user_seconds=usage.ru_utime,
        system_seconds=usage.ru_stime,
    )
    stdout_path.unlink()
    stderr_path.unlink()
    return sample


def latency_statistics(samples_ns: list[int], cycles: int) -> dict[str, float]:
    """Summarise command wall times with percentiles and cycle throughput.

    Parameters
    ----------
    samples_ns
        At least ``MIN_SAMPLES`` positive wall times in nanoseconds.
    cycles
        Control cycles analysed by one command.

    Returns
    -------
    dict[str, float]
        P50, P95, P99, mean, minimum and maximum in milliseconds, and analysed cycles per
        second of the mean.

    Raises
    ------
    ValueError
        If there are fewer than ``MIN_SAMPLES`` samples or one is not positive.
    """
    if len(samples_ns) < MIN_SAMPLES or any(sample <= 0 for sample in samples_ns):
        message = f"statistics require {MIN_SAMPLES} positive samples"
        raise ValueError(message)
    values = [sample / 1e6 for sample in samples_ns]
    percentiles = statistics.quantiles(values, n=100, method="inclusive")
    mean = statistics.mean(values)
    return {
        "p50_ms": statistics.median(values),
        "p95_ms": percentiles[94],
        "p99_ms": percentiles[98],
        "mean_ms": mean,
        "min_ms": min(values),
        "max_ms": max(values),
        "throughput_cycles_per_second": cycles / (mean / 1e3),
    }
