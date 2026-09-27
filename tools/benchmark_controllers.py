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
    if not 1 <= warmup <= MAX_REPEATS or not MIN_REPEATS <= repeats <= MAX_REPEATS:
        message = "warmup must be [1,1000] and repeats [5,1000]"
        raise ValueError(message)
    allowed = sorted(os.sched_getaffinity(0))
    if cpu not in allowed:
        message = "benchmark CPU is outside inherited affinity"
        raise ValueError(message)
    if output.exists():
        raise FileExistsError(output)
    paths = {name: root / name for name in (*SOURCES, *BINARIES.values())}
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    producers = ("tools/benchmark_controllers.py", "tools/benchmark_batches.py")
    if any(
        before[name] != hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in producers
    ):
        message = "snapshot benchmark producer differs from executing producer"
        raise ValueError(message)
    versions = {
        tool: subprocess.run(
            [tool, "--version"], check=True, capture_output=True, text=True, timeout=10
        ).stdout.splitlines()[0]
        for tool in ("gcc", "rustc", "cargo", "taskset")
    }
    load_before = os.getloadavg()
    rows: list[dict[str, Any]] = []
    checksums: dict[str, int] = {}
    for repeat in range(warmup + repeats):
        for backend, binary in BINARIES.items():
            command = ["taskset", "--cpu-list", str(cpu), str(root / binary)]
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            for controller, iterations, elapsed, checksum in decode_batch(result.stdout):
                if checksums.setdefault(controller, checksum) != checksum:
                    message = "native benchmark checksum parity failed"
                    raise ValueError(message)
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
    after = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if before != after:
        message = "benchmark source or binary changed during measurement"
        raise ValueError(message)
    summaries = [
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
    cpu_info = (Path("/proc/cpuinfo")).read_text()
    cpu_model = next(
        line.split(":", 1)[1].strip()
        for line in cpu_info.splitlines()
        if line.startswith("model name")
    )
    cpu_root = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq")
    frequency = {
        path.name: path.read_text().strip()
        for path in cpu_root.glob("scaling_*")
        if path.name
        in {
            "scaling_governor",
            "scaling_cur_freq",
            "scaling_min_freq",
            "scaling_max_freq",
            "scaling_driver",
        }
    }
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    artifact = {
        "schema": "loop-timing-witness.controller-comparison.v1",
        "recorded_utc": datetime.now(UTC).isoformat(),
        "base_commit": commit,
        "evidence_status": "nonisolated_regression_only",
        "production_performance_claim": False,
        "parameters": {"warmup": warmup, "repeats": repeats, "iterations": ITERATIONS},
        "source_and_binary_sha256": before,
        "host": {
            "cpu_model": cpu_model,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "toolchains": versions,
            "inherited_affinity": allowed,
            "child_affinity": [cpu],
            "isolation": "taskset pin only; no CPU reservation or cpuset shielding",
            "load_before": load_before,
            "load_after": os.getloadavg(),
            "frequency_context": frequency,
            "other_heavy_jobs": "not excluded; shared workstation",
        },
        "commands": {
            backend: ["taskset", "--cpu-list", str(cpu), str(root / binary)]
            for backend, binary in BINARIES.items()
        },
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
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"controller benchmark: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"controller benchmark: PASS: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
