# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Python and native control-run analysis timing on closed-loop data

"""Time both published analysis commands on every repeat of a campaign and on the campaign.

Each pass runs, for every repeat run and then for the campaign, the Python command and the
native command once each, pinned to one CPU. Every pass checks that both commands exit with
the same status, print the same text and publish byte-identical reports; a difference
refuses the whole measurement. Warm-up passes are kept in the raw samples and excluded from
the statistics. Source and binary digests are checked before and after.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from timed_command import MIN_SAMPLES, TimedSample, latency_statistics, run_timed

from loop_timing_witness.host_profile import scaled
from manifest_io import canonical_json_bytes, load_json_object, sha256_of_file

ROOT: Final = Path(__file__).resolve().parents[1]
SCHEMA: Final = "loop-timing-witness.control-run-analysis-benchmark.v1"
BACKENDS: Final = ("python", "native")
NATIVE_PROGRAMS: Final = {
    "run": "loop-timing-witness-analyze-native",
    "campaign": "loop-timing-witness-campaign-native",
}
PYTHON_MODULES: Final = {
    "run": "loop_timing_witness.analyze_run",
    "campaign": "loop_timing_witness.analyze_campaign",
}
PRODUCERS: Final = ("tools/benchmark_control_runs.py", "tools/timed_command.py")
EVIDENCE: Final = {"ci": "fixed_hosted_runner", "local": "nonisolated_workstation"}
MAX_WARMUP: Final = 10
MAX_PASSES: Final = 100
HANG_GUARD_SECONDS: Final = 3600
"""Policy hang guard for one analysis command; it is not a performance budget."""
CLOCK: Final = "time.perf_counter_ns from process creation to reaping; os.wait4 resource use"
SCOPE: Final = (
    "Wall time of the published host analysis commands on deterministic closed-loop RTL "
    "simulation data; not controller, processor or hardware timing."
)


@dataclass(frozen=True, slots=True)
class Operation:
    """One analysed target: a repeat run or the whole campaign.

    Attributes
    ----------
    name
        ``run`` or ``campaign``.
    target
        Run manifest or campaign manifest.
    cycles
        Control cycles the command analyses.
    """

    name: str
    target: Path
    cycles: int


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    """One requested measurement.

    Attributes
    ----------
    campaign
        Closed-loop campaign manifest.
    native
        Directory holding both native commands.
    output
        New benchmark artefact.
    cpu
        CPU in the caller's allowed set for every child.
    warmup
        Warm-up passes, excluded from the statistics.
    passes
        Measured passes.
    label
        ``ci`` or ``local``.
    """

    campaign: Path
    native: Path
    output: Path
    cpu: int
    warmup: int
    passes: int
    label: str


def operations(campaign: Path) -> list[Operation]:
    """Return every repeat run in campaign order, then the campaign itself.

    Parameters
    ----------
    campaign
        Campaign manifest whose repeats bind their run manifests by relative path.

    Returns
    -------
    list[Operation]
        One run operation per repeat and one campaign operation over all their cycles.

    Raises
    ------
    ValueError
        If the campaign manifest has no repeat list of bound run manifests.
    OSError
        If a manifest cannot be read.
    """
    runs = []
    try:
        for entry in load_json_object(campaign)["repeats"]:
            manifest = campaign.parent / entry["run_manifest"]["path"]
            runs.append(Operation("run", manifest, load_json_object(manifest)["cycle_count"]))
    except (KeyError, TypeError) as error:
        message = "campaign manifest does not bind its repeat runs"
        raise ValueError(message) from error
    return [*runs, Operation("campaign", campaign, sum(item.cycles for item in runs))]


def command(operation: Operation, backend: str, native: Path, output: Path) -> list[str]:
    """Return the published command of one backend for one operation.

    Parameters
    ----------
    operation
        Run or campaign to analyse.
    backend
        ``python`` or ``native``.
    native
        Directory holding both native commands.
    output
        New report directory.

    Returns
    -------
    list[str]
        Argument vector.
    """
    if backend == "python":
        program = [sys.executable, "-m", PYTHON_MODULES[operation.name]]
    else:
        program = [str(native / NATIVE_PROGRAMS[operation.name])]
    return [*program, str(operation.target), "--output-dir", str(output)]


def measure(
    request: BenchmarkRequest, operation: Operation, backend: str, work: Path
) -> tuple[dict[str, Any], tuple[int, str, dict[str, str]]]:
    """Run one command once and return its sample row and comparable outcome.

    Parameters
    ----------
    request
        Requested measurement.
    operation
        Run or campaign to analyse.
    backend
        ``python`` or ``native``.
    work
        Owned working directory; the report is removed after it is read.

    Returns
    -------
    tuple
        The raw sample row, and the status, printed text with the report path
        replaced, and the SHA-256 of every published report file.

    Raises
    ------
    ValueError
        If the command fails; a run analysis exits 0 and a campaign 0 or 2.
    """
    output = work / f"{backend}-report"
    sample = run_timed(
        command(operation, backend, request.native, output),
        request.cpu,
        work,
        scaled(HANG_GUARD_SECONDS),
    )
    if sample.status not in ({0} if operation.name == "run" else {0, 2}):
        message = f"{backend} {operation.name} analysis failed with status {sample.status}"
        raise ValueError(message)
    files = {path.name: sha256_of_file(path) for path in sorted(output.iterdir()) if path.is_file()}
    shutil.rmtree(output)
    printed = (sample.stdout + sample.stderr).replace(str(output), "<report>")
    return sample_row(operation, backend, sample), (sample.status, printed, files)


def sample_row(operation: Operation, backend: str, sample: TimedSample) -> dict[str, Any]:
    """Return the raw artefact row of one timed command.

    Parameters
    ----------
    operation
        Analysed run or campaign.
    backend
        ``python`` or ``native``.
    sample
        The reaped command.

    Returns
    -------
    dict[str, Any]
        Operation, target, backend, status, wall time and resource use.
    """
    return {
        "operation": operation.name,
        "target": operation.target.name
        if operation.name == "campaign"
        else operation.target.parent.name,
        "backend": backend,
        "status": sample.status,
        "elapsed_ns": sample.elapsed_ns,
        "max_rss_kib": sample.max_rss_kib,
        "user_seconds": sample.user_seconds,
        "system_seconds": sample.system_seconds,
    }


def measure_pass(
    request: BenchmarkRequest, plan: list[Operation], work: Path, phase: str, index: int
) -> list[dict[str, Any]]:
    """Run every operation with both backends once and hold their outcomes equal.

    Parameters
    ----------
    request
        Requested measurement.
    plan
        Operations in order.
    work
        Owned working directory.
    phase
        ``warmup`` or ``measured``.
    index
        Pass index within its phase.

    Returns
    -------
    list[dict[str, Any]]
        Raw sample rows of this pass.

    Raises
    ------
    ValueError
        If a command fails or the backends differ in status, text or report bytes.
    """
    rows = []
    for operation in plan:
        outcomes = []
        for backend in BACKENDS:
            row, outcome = measure(request, operation, backend, work)
            rows.append({**row, "phase": phase, "pass": index})
            outcomes.append(outcome)
        if outcomes[0] != outcomes[1]:
            message = f"Python and native {operation.name} outcomes differ"
            raise ValueError(message)
    return rows


def digests(request: BenchmarkRequest, plan: list[Operation]) -> dict[str, str]:
    """Return the SHA-256 of the producers, both native commands and every analysed input.

    Parameters
    ----------
    request
        Requested measurement.
    plan
        Operations in order.

    Returns
    -------
    dict[str, str]
        Digest by role and name.
    """
    named = {f"producer:{name}": ROOT / name for name in PRODUCERS}
    named |= {f"native:{name}": request.native / name for name in NATIVE_PROGRAMS.values()}
    named[f"campaign:{request.campaign.name}"] = request.campaign
    for operation in plan[:-1]:
        repeat = operation.target.parent
        for name in ("manifest.json", "events.bin", "tracking.csv", "stimulus.json"):
            named[f"{repeat.name}:{name}"] = repeat / name
    return {name: sha256_of_file(path) for name, path in named.items()}


def host(cpu: int) -> dict[str, Any]:
    """Return the executing host's CPU, platform, toolchain, affinity and load context.

    Parameters
    ----------
    cpu
        CPU every child is pinned to.

    Returns
    -------
    dict[str, Any]
        Host provenance for the artefact.
    """
    model = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines()
            if line.startswith("model name")
        ),
        "unknown",
    )
    frequency = Path(f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor")
    return {
        "cpu_model": model,
        "logical_cpus": os.cpu_count(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "toolchains": {
            tool: subprocess.run(
                [tool, "--version"], check=True, capture_output=True, text=True, timeout=scaled(10)
            ).stdout.splitlines()[0]
            for tool in ("rustc", "verilator", "taskset")
        },
        "inherited_affinity": sorted(os.sched_getaffinity(0)),
        "child_affinity": [cpu],
        "isolation": "taskset pin only; no CPU reservation or cpuset shielding",
        "scaling_governor": frequency.read_text().strip() if frequency.is_file() else None,
        "load_average": list(os.getloadavg()),
    }


def results(rows: list[dict[str, Any]], plan: list[Operation]) -> list[dict[str, Any]]:
    """Summarise the measured samples of each operation and backend.

    Parameters
    ----------
    rows
        Every raw sample row.
    plan
        Operations in order; every run operation has the same cycle count.

    Returns
    -------
    list[dict[str, Any]]
        One measured row per operation and backend, run before campaign.
    """
    cycles = {operation.name: operation.cycles for operation in plan}
    summary = []
    for name in ("run", "campaign"):
        for backend in BACKENDS:
            measured = [
                row
                for row in rows
                if row["phase"] == "measured"
                and row["operation"] == name
                and row["backend"] == backend
            ]
            summary.append(
                {
                    "name": name,
                    "backend": backend,
                    "status": "measured",
                    "samples": len(measured),
                    "cycles_per_command": cycles[name],
                    "stats": latency_statistics(
                        [row["elapsed_ns"] for row in measured], cycles[name]
                    ),
                    "max_rss_kib": max(row["max_rss_kib"] for row in measured),
                }
            )
    return summary


def validate(request: BenchmarkRequest) -> None:
    """Refuse a request whose parameters, CPU, output or native commands are unusable.

    Parameters
    ----------
    request
        Requested measurement.

    Raises
    ------
    ValueError
        With the first refused condition.
    """
    if not 0 <= request.warmup <= MAX_WARMUP:
        message = f"warmup must be in [0, {MAX_WARMUP}]"
        raise ValueError(message)
    if not MIN_SAMPLES <= request.passes <= MAX_PASSES:
        message = f"passes must be in [{MIN_SAMPLES}, {MAX_PASSES}]"
        raise ValueError(message)
    if request.cpu not in os.sched_getaffinity(0):
        message = "benchmark CPU is outside the inherited affinity"
        raise ValueError(message)
    if request.output.exists():
        message = "output already exists"
        raise ValueError(message)
    if not all((request.native / name).is_file() for name in NATIVE_PROGRAMS.values()):
        message = "native analysis commands are missing"
        raise ValueError(message)


def benchmark(request: BenchmarkRequest, work: Path) -> dict[str, Any]:
    """Measure every pass and return the complete artefact.

    Parameters
    ----------
    request
        Requested measurement.
    work
        Owned, empty working directory.

    Returns
    -------
    dict[str, Any]
        The benchmark artefact.

    Raises
    ------
    ValueError
        If the request is refused, a command fails, the backends differ or an input changes.
    """
    validate(request)
    plan = operations(request.campaign)
    before = digests(request, plan)
    context = host(request.cpu)
    rows = []
    for index in range(request.warmup):
        rows.extend(measure_pass(request, plan, work, "warmup", index))
    for index in range(request.passes):
        rows.extend(measure_pass(request, plan, work, "measured", index))
    if digests(request, plan) != before:
        message = "a producer, native command or input changed during measurement"
        raise ValueError(message)
    context["load_average_after"] = list(os.getloadavg())
    return assemble(request, plan, rows, before, context)


def parameters(request: BenchmarkRequest, plan: list[Operation]) -> dict[str, int]:
    """Return the pass counts and the campaign shape of the measurement.

    Parameters
    ----------
    request
        Requested measurement.
    plan
        Operations in order; the last is the campaign.

    Returns
    -------
    dict[str, int]
        Warm-up and measured passes, repeats and cycles per repeat.
    """
    return {
        "warmup_passes": request.warmup,
        "measured_passes": request.passes,
        "repeats": len(plan) - 1,
        "cycles_per_repeat": plan[0].cycles,
    }


def base_commit() -> str:
    """Return the repository commit the measurement ran at.

    Returns
    -------
    str
        Full ``HEAD`` commit of the executing repository.
    """
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=scaled(10),
    ).stdout.strip()


def assemble(
    request: BenchmarkRequest,
    plan: list[Operation],
    rows: list[dict[str, Any]],
    before: dict[str, str],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Return the artefact from the measured rows and the recorded provenance.

    Parameters
    ----------
    request
        Requested measurement.
    plan
        Operations in order.
    rows
        Every raw sample row.
    before
        Digests taken before measurement, equal to those after it.
    context
        Host provenance, including the load average after measurement.

    Returns
    -------
    dict[str, Any]
        The benchmark artefact.
    """
    summary = results(rows, plan)
    mean = {(item["name"], item["backend"]): item["stats"]["mean_ms"] for item in summary}
    return {
        "schema": SCHEMA,
        "recorded_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_commit": base_commit(),
        "evidence_status": EVIDENCE[request.label],
        "scope": SCOPE,
        "parameters": parameters(request, plan),
        "sha256": before,
        "host": context,
        "clock": CLOCK,
        "percentile_method": "inclusive linear interpolation",
        "results": summary,
        "native_speedup_of_mean": {
            name: mean[(name, "python")] / mean[(name, "native")] for name in ("run", "campaign")
        },
        "raw_samples": rows,
    }


def main(argv: list[str] | None = None) -> int:
    """Write one benchmark artefact or refuse with one line on standard error.

    Parameters
    ----------
    argv
        Command arguments; ``None`` reads the process arguments.

    Returns
    -------
    int
        Zero for a written artefact, one for a refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--passes", type=int, default=5)
    parser.add_argument("--label", choices=sorted(EVIDENCE), required=True)
    args = parser.parse_args(argv)
    request = BenchmarkRequest(
        args.campaign.resolve(),
        args.native.resolve(),
        args.output,
        args.cpu,
        args.warmup,
        args.passes,
        args.label,
    )
    try:
        work = Path(tempfile.mkdtemp(prefix=f".{args.output.name}.", dir=args.output.parent))
    except OSError as error:
        print(f"control-run benchmark refused: {error}", file=sys.stderr)
        return 1
    try:
        artifact = benchmark(request, work)
        with args.output.open("xb") as destination:
            destination.write(canonical_json_bytes(artifact))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"control-run benchmark refused: {error}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(work)
    print(f"control-run benchmark: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
