# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — reproducible native controller comparison

"""Measure matching C/Rust kernels and retain raw local regression evidence."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark_batches import ITERATIONS, MIN_REPEATS, benchmark_statistics, decode_batch

from loop_timing_witness.host_profile import scaled
from manifest_io import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
MAX_REPEATS = 1000
SOURCES = (
    "Makefile",
    "tools/benchmark_controllers.py",
    "tools/benchmark_batches.py",
    "controllers/c/witness_controller.c",
    "controllers/c/witness_controller.h",
    "benchmarks/controller_benchmark.c",
    "controllers/rust/src/lib.rs",
    "controllers/rust/src/bin/controller_benchmark.rs",
    "controllers/rust/Cargo.toml",
    "controllers/rust/Cargo.lock",
)
BINARIES = {
    "c": "build/controller_benchmark",
    "rust": "controllers/rust/target/release/controller_benchmark",
}


class BenchmarkRefusedError(ValueError):
    """A deliberately authored refusal of invalid measurement or source identity."""


_FIXED_CONTEXT: dict[str, object] = {
    "schema": "loop-timing-witness.controller-comparison.v1",
    "evidence_status": "nonisolated_regression_only",
    "production_performance_claim": False,
    "clock": {"c": "CLOCK_MONOTONIC", "rust": "std::time::Instant"},
    "statistic_scope": "percentiles of million-step batch means; not per-step tails",
    "percentile_method": "inclusive linear interpolation",
    "ci_evidence": {
        "status": "not_attested",
        "reason": "verify hosted workflow receipt separately",
    },
    "rtl_timing": {
        "status": "not_comparable",
        "reason": "simulated fabric ticks are not host wall time",
    },
}
_FREQUENCY_FILES = frozenset(
    {
        "scaling_governor",
        "scaling_cur_freq",
        "scaling_min_freq",
        "scaling_max_freq",
        "scaling_driver",
    }
)


def _commands(root: Path, cpu: int) -> dict[str, list[str]]:
    """Return each backend's pinned benchmark command.

    Parameters
    ----------
    root
        Checkout or frozen snapshot containing the built native binaries.
    cpu
        Child CPU.

    Returns
    -------
    dict[str, list[str]]
        ``taskset`` vector of every backend's binary.
    """
    return {
        backend: ["taskset", "--cpu-list", str(cpu), str(root / binary)]
        for backend, binary in BINARIES.items()
    }


def _tool_versions() -> dict[str, str]:
    """Return the first version line of each toolchain command.

    Returns
    -------
    dict[str, str]
        Version line of gcc, rustc, cargo and taskset.
    """
    return {
        tool: subprocess.run(
            [tool, "--version"], check=True, capture_output=True, text=True, timeout=scaled(10)
        ).stdout.splitlines()[0]
        for tool in ("gcc", "rustc", "cargo", "taskset")
    }


def _check_unchanged(paths: dict[str, Path], before: dict[str, str]) -> None:
    """Require every measured source and binary to be unchanged after measuring.

    Parameters
    ----------
    paths
        Measured sources and binaries.
    before
        Their digests before measuring.

    Raises
    ------
    BenchmarkRefusedError
        If any digest differs.
    """
    after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if before != after:
        message = "benchmark source or binary changed during measurement"
        raise BenchmarkRefusedError(message)


def _head(root: Path) -> str:
    """Return the commit of the measured checkout.

    Parameters
    ----------
    root
        Measured checkout.

    Returns
    -------
    str
        Full ``HEAD`` commit.
    """
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=scaled(10),
    ).stdout.strip()


def _check_request(output: Path, cpu: int, warmup: int, repeats: int) -> list[int]:
    """Refuse invalid batch counts, a CPU outside the affinity or an existing output.

    Parameters
    ----------
    output
        New JSON artifact path.
    cpu
        Requested child CPU.
    warmup, repeats
        Discarded and measured batches per backend.

    Returns
    -------
    list[int]
        The inherited allowed CPUs, sorted.

    Raises
    ------
    BenchmarkRefusedError
        If a count is out of range or the CPU is not allowed.
    FileExistsError
        If the output already exists.
    """
    if not 1 <= warmup <= MAX_REPEATS or not MIN_REPEATS <= repeats <= MAX_REPEATS:
        message = "warmup must be [1,1000] and repeats [5,1000]"
        raise BenchmarkRefusedError(message)
    allowed = sorted(os.sched_getaffinity(0))
    if cpu not in allowed:
        message = "benchmark CPU is outside inherited affinity"
        raise BenchmarkRefusedError(message)
    if output.exists():
        raise FileExistsError(output)
    return allowed


def _snapshot(root: Path) -> tuple[dict[str, Path], dict[str, str]]:
    """Hash the measured sources and binaries and require the executing producers.

    Parameters
    ----------
    root
        Checkout or frozen snapshot containing the built native binaries.

    Returns
    -------
    tuple[dict[str, Path], dict[str, str]]
        Paths and digests of every source and binary.

    Raises
    ------
    BenchmarkRefusedError
        If the snapshot's producers differ from the executing ones.
    """
    paths = {name: root / name for name in (*SOURCES, *BINARIES.values())}
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    producers = ("tools/benchmark_controllers.py", "tools/benchmark_batches.py")
    if any(
        before[name] != hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in producers
    ):
        message = "snapshot benchmark producer differs from executing producer"
        raise BenchmarkRefusedError(message)
    return paths, before


def _measure(root: Path, cpu: int, warmup: int, repeats: int) -> list[dict[str, Any]]:
    """Run interleaved warm-up and measured batches of both backends on one CPU.

    Parameters
    ----------
    root
        Checkout or frozen snapshot containing the built native binaries.
    cpu
        Child CPU.
    warmup, repeats
        Discarded and measured batches per backend.

    Returns
    -------
    list[dict[str, Any]]
        One row per controller per batch, warm-up rows included.

    Raises
    ------
    BenchmarkRefusedError
        If a controller's command checksum differs between batches or backends.
    """
    rows: list[dict[str, Any]] = []
    checksums: dict[str, int] = {}
    for repeat in range(warmup + repeats):
        for backend, binary in BINARIES.items():
            command = ["taskset", "--cpu-list", str(cpu), str(root / binary)]
            result = subprocess.run(
                command, check=True, capture_output=True, text=True, timeout=scaled(30)
            )
            for controller, iterations, elapsed, checksum in decode_batch(result.stdout):
                if checksums.setdefault(controller, checksum) != checksum:
                    message = "native benchmark checksum parity failed"
                    raise BenchmarkRefusedError(message)
                rows.append(
                    {
                        "backend": backend,
                        "controller": controller,
                        "phase": "warmup" if repeat < warmup else "measured",
                        "repeat": repeat if repeat < warmup else repeat - warmup,
                        "iterations": iterations,
                        "total_ns": elapsed,
                        "command_checksum": checksum,
                    }
                )
    return rows


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarise the measured batches of each backend and controller.

    Parameters
    ----------
    rows
        Every batch row.

    Returns
    -------
    list[dict[str, Any]]
        Statistics of each backend's PID and LQR batches, in backend order.
    """
    return [
        {
            "backend": backend,
            "controller": controller,
            "stats": benchmark_statistics(
                [
                    row["total_ns"]
                    for row in rows
                    if row["backend"] == backend
                    and row["controller"] == controller
                    and row["phase"] == "measured"
                ]
            ),
        }
        for backend in BINARIES
        for controller in ("pid", "lqr")
    ]


def _host(
    cpu: int, allowed: list[int], versions: dict[str, str], load_before: tuple[float, float, float]
) -> dict[str, object]:
    """Return the host context of the measurement, without the closing load.

    Parameters
    ----------
    cpu
        Child CPU.
    allowed
        Inherited allowed CPUs.
    versions
        Toolchain version lines.
    load_before
        Load average before measuring.

    Returns
    -------
    dict[str, object]
        Processor model, platform, Python, toolchains, affinity, isolation,
        opening load and the child CPU's frequency context.
    """
    cpu_model = next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    )
    cpu_root = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq")
    return {
        "cpu_model": cpu_model,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "toolchains": versions,
        "inherited_affinity": allowed,
        "child_affinity": [cpu],
        "isolation": "taskset pin only; no CPU reservation or cpuset shielding",
        "load_before": load_before,
        "frequency_context": {
            path.name: path.read_text().strip()
            for path in cpu_root.glob("scaling_*")
            if path.name in _FREQUENCY_FILES
        },
        "other_heavy_jobs": "not excluded; shared workstation",
    }


def measure_controllers(
    output: Path, cpu: int, warmup: int = 3, repeats: int = 20, *, root: Path = ROOT
) -> None:
    """Run both actual native benchmarks with child-only affinity and exclusive output.

    Parameters
    ----------
    output
        New JSON artifact; an existing path is never overwritten.
    cpu
        CPU in the caller's inherited allowed set; pinning does not reserve the core.
    warmup
        Complete discarded batches per backend, between one and one thousand.
    repeats
        Complete measured batches per backend, between five and one thousand.

    root
        Checkout or frozen source snapshot containing the built native binaries.

    Raises
    ------
    ValueError
        If parameters, native protocol, checksum parity or artifact identity fail.
    OSError
        If actual binaries, source files or output cannot be accessed.
    subprocess.SubprocessError
        If an actual native process fails or exceeds its bounded lifetime.
    """
    allowed = _check_request(output, cpu, warmup, repeats)
    paths, before = _snapshot(root)
    versions = _tool_versions()
    load_before = os.getloadavg()
    rows = _measure(root, cpu, warmup, repeats)
    _check_unchanged(paths, before)
    summaries = _summaries(rows)
    host = _host(cpu, allowed, versions, load_before)
    commit = _head(root)
    artifact = {
        **_FIXED_CONTEXT,
        "recorded_utc": datetime.now(UTC).isoformat(),
        "base_commit": commit,
        "parameters": {"warmup": warmup, "repeats": repeats, "iterations": ITERATIONS},
        "source_and_binary_sha256": before,
        "host": {**host, "load_after": os.getloadavg()},
        "commands": _commands(root, cpu),
        "raw_batches": rows,
        "results": summaries,
    }
    with output.open("xb") as destination:
        destination.write(canonical_json_bytes(artifact))


def main(argv: list[str] | None = None) -> int:
    """Write a bounded source-bound native comparison from the public CLI.

    Parameters
    ----------
    argv
        Explicit arguments or process command line.

    Returns
    -------
    int
        Zero after comparison, one after a refused or failed actual measurement.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        measure_controllers(args.output, args.cpu, args.warmup, args.repeats, root=args.source_root)
    except BenchmarkRefusedError as error:
        print(f"controller benchmark: FAIL: {error}", file=sys.stderr)
        return 1
    except ValueError, OSError, subprocess.SubprocessError:
        print("controller benchmark: FAIL: could not complete measurement", file=sys.stderr)
        return 1
    print(f"controller benchmark: PASS: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
