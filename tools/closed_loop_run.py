# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — closed-loop benchmark runs and their repeat campaign

"""Run the closed-loop harness and bind each repeat into a hash-bound run and campaign.

Each repeat directory holds the drained events, the raw plant trajectory, the tracking
series derived from it, the stimulus declaration, the harness summary, the measurement
domain and a snapshot of every source and the harness binary, all bound by SHA-256 in
the run manifest. Power is ``null``: RTL simulation has no power monitor, so every report
states that its power series is unavailable. A failed repeat keeps its evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from closed_loop_stimulus import (
    COEFFICIENTS,
    FAULT_LEAD,
    FAULT_PERIODS,
    PERIOD_TICKS,
    SCALE,
    declaration,
    expected_counts,
    harness_arguments,
)
from native_simulation_manifest import file_reference

from loop_timing_witness.host_profile import build_jobs, scaled
from manifest_io import canonical_json_bytes, sha256_of_file

ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_HARNESS: Final = ROOT / "build/closed_loop/closed_loop_harness"
HARNESS_SOURCES: Final = (
    "Makefile",
    "benchmarks/closed_loop_harness.cpp",
    "controllers/c/witness_controller.c",
    "controllers/c/witness_controller.h",
)
MAXIMUM_REPEATS: Final = 64
HANG_GUARD_TICKS_PER_SECOND: Final = 100_000
"""Policy hang guard: the slowest simulation rate a repeat may run at before it is stopped.

It is not a performance budget; measured rates are an order of magnitude higher.
"""
CONTROLLER: Final = {"name": "pid_anti_windup", "coefficients": COEFFICIENTS}
PLANT: Final = {
    "name": "second_order_mechanical",
    "fixed_point_format": "Q8.24",
    "tracking_unit": "model_output",
}
INSTRUMENT_FLAGS: Final = {
    "floor_ticks": None,
    "known_period_pass": False,
    "injected_delay_pass": False,
    "overflow_pass": False,
    "bus_offset_pass": False,
}
ENVIRONMENT: Final = {"room_temperature_c": None, "board_supply_only": False}
OPERATOR_NOTES: Final = (
    "Verilator simulation of the production closed loop control_plant_witness with a "
    "declared deterministic service stimulus (stimulus.json); commands come from the "
    "production C PID kernel. No processor execution timing, power or board acceptance."
)


@dataclass(frozen=True, slots=True)
class CampaignRequest:
    """One requested closed-loop campaign.

    Attributes
    ----------
    output
        New campaign directory.
    cycles
        Control cycles of each repeat.
    repeats
        Number of repeats; repeat ``i`` uses seed ``seed + i - 1``.
    seed
        Seed of the first repeat.
    harness
        Built harness executable.
    jobs
        Concurrent repeats.
    """

    output: Path
    cycles: int
    repeats: int
    seed: int
    harness: Path
    jobs: int


def snapshot_sources(run: Path) -> list[Path]:
    """Copy the RTL, harness, controller and build recipe into the run's source snapshot.

    Parameters
    ----------
    run
        New repeat directory.

    Returns
    -------
    list[Path]
        Copied files, sorted by repository path.
    """
    originals = sorted([*(ROOT / "rtl").glob("*.sv"), *(ROOT / name for name in HARNESS_SOURCES)])
    copies = []
    for original in originals:
        destination = run / "source" / original.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        copies.append(destination)
    return copies


def run_harness(harness: Path, run: Path, cycles: int, seed: int) -> dict[str, Any]:
    """Execute the harness for one repeat and check its summary against the declaration.

    Parameters
    ----------
    harness
        Built harness executable.
    run
        Repeat directory receiving ``events.bin``, ``trajectory.csv`` and ``summary.json``.
    cycles
        Control cycles of the repeat.
    seed
        Seed of the service offset sequence.

    Returns
    -------
    dict[str, Any]
        Harness summary.

    Raises
    ------
    ValueError
        If the harness refuses or its counts differ from the declared stimulus.
    """
    arguments = harness_arguments(cycles, seed)
    timeout = scaled(60 + math.ceil(cycles * PERIOD_TICKS / HANG_GUARD_TICKS_PER_SECOND))
    result = subprocess.run(
        [
            str(harness),
            str(run / "events.bin"),
            str(run / "trajectory.csv"),
            *(f"{key}={value}" for key, value in arguments.items()),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    (run / "harness.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        message = f"harness refused repeat: {result.stderr.strip()}"
        raise ValueError(message)
    summary = checked_summary(result.stdout, cycles)
    (run / "summary.json").write_bytes(canonical_json_bytes(summary))
    return summary


def checked_summary(text: str, cycles: int) -> dict[str, Any]:
    """Parse the harness summary and hold it to the counts the declared stimulus fixes.

    Parameters
    ----------
    text
        The harness's standard output, one JSON object.
    cycles
        Control cycles of the repeat.

    Returns
    -------
    dict[str, Any]
        The summary.

    Raises
    ------
    ValueError
        If the output is not a JSON object or a declared count, the overflow or the safe
        state differs.
    """
    summary = json.loads(text)
    required = {"cycles": cycles, "overflow": 0, "safe": True, **expected_counts(cycles)}
    if not isinstance(summary, dict) or any(
        summary.get(name) != value for name, value in required.items()
    ):
        message = "harness summary differs from the declared stimulus"
        raise ValueError(message)
    return summary


def write_tracking(run: Path) -> None:
    """Convert the raw Q8.24 trajectory to the reference and output tracking series.

    Parameters
    ----------
    run
        Repeat directory holding ``trajectory.csv``.
    """
    with (run / "trajectory.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    (run / "tracking.csv").write_text(
        "cycle,reference,output\n"
        + "".join(
            f"{row['cycle']},{int(row['reference']) / SCALE},{int(row['output']) / SCALE}\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def source_block(run: Path, sources: list[Path]) -> dict[str, Any]:
    """Return the manifest's source declaration with the installed Verilator version.

    Parameters
    ----------
    run
        Repeat directory.
    sources
        Snapshotted sources, binary and provenance files within the run.

    Returns
    -------
    dict[str, Any]
        ``rtl_simulation`` source with every file bound by SHA-256.
    """
    version = subprocess.run(
        ["verilator", "--version"], check=True, text=True, capture_output=True, timeout=scaled(10)
    ).stdout.splitlines()[0]
    return {
        "kind": "rtl_simulation",
        "tool": "Verilator",
        "version": version,
        "files": [file_reference(run, path) for path in sources],
    }


def run_manifest(
    run: Path, cycles: int, started: str, summary: dict[str, Any], sources: list[Path]
) -> dict[str, Any]:
    """Return the hash-bound run manifest of one finished repeat.

    Parameters
    ----------
    run
        Repeat directory.
    cycles
        Control cycles of the repeat.
    started
        UTC time immediately before the harness started.
    summary
        Checked harness summary.
    sources
        Snapshotted sources, binary and provenance files within the run.

    Returns
    -------
    dict[str, Any]
        Run manifest of schema ``loop-timing-witness.run-manifest.v1``.
    """
    fault = {"cycle": cycles - FAULT_LEAD, "kind": "delay", "delay_periods": FAULT_PERIODS}
    return {
        "schema": "loop-timing-witness.run-manifest.v1",
        "run_id": f"closed-loop-{run.name}",
        "started_utc": started,
        "source": source_block(run, sources),
        "measurement_domain": file_reference(run, run / "measurement-domain.json"),
        "profile": "CONTROL",
        "placement": "bare_metal_amp",
        "sample_period_ticks": PERIOD_TICKS,
        "cycle_count": cycles,
        "warmup_cycles": 0,
        "load_case": "simulated_service",
        "controller": CONTROLLER,
        "plant": PLANT,
        "fault_schedule": [fault],
        "files": {
            "events": file_reference(run, run / "events.bin"),
            "tracking": file_reference(run, run / "tracking.csv"),
            "power": None,
        },
        "hardware_artifacts": None,
        "instrument": {"fifo_overflow_count": summary["overflow"], **INSTRUMENT_FLAGS},
        "environment": ENVIRONMENT,
        "operator_notes": OPERATOR_NOTES,
    }


def capture_repeat(
    harness: Path, campaign: Path, index: int, cycles: int, seed: int
) -> dict[str, Any]:
    """Produce one repeat directory and return its campaign entry.

    Parameters
    ----------
    harness
        Built harness executable.
    campaign
        Campaign directory.
    index
        One-based repeat index.
    cycles
        Control cycles of the repeat.
    seed
        Seed of this repeat's service offsets.

    Returns
    -------
    dict[str, Any]
        Repeat entry binding the run manifest by path and SHA-256.
    """
    run = campaign / f"repeat-{index}"
    run.mkdir()
    sources = snapshot_sources(run)
    shutil.copyfile(ROOT / "measurement-domain.json", run / "measurement-domain.json")
    (run / "stimulus.json").write_bytes(canonical_json_bytes(declaration(cycles, seed)))
    binary = run / "closed_loop_harness"
    shutil.copy2(harness, binary)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = run_harness(binary, run, cycles, seed)
    write_tracking(run)
    provenance = [
        binary,
        *(run / name for name in ("stimulus.json", "summary.json", "trajectory.csv")),
    ]
    manifest = run_manifest(run, cycles, started, summary, [*sources, *provenance])
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "repeat_index": index,
        "run_manifest": {
            "path": f"repeat-{index}/manifest.json",
            "sha256": sha256_of_file(run / "manifest.json"),
        },
        "rebooted_before_run": False,
    }


def capture_campaign(request: CampaignRequest) -> Path:
    """Produce every repeat, in parallel up to ``request.jobs``, and write the campaign manifest.

    Parameters
    ----------
    request
        Requested campaign.

    Returns
    -------
    Path
        Campaign manifest path.

    Raises
    ------
    ValueError
        If an argument is outside its range, the output exists or the harness is absent.
    """
    output, repeats = request.output, request.repeats
    if not 1 <= repeats <= MAXIMUM_REPEATS:
        message = f"repeats must be in [1, {MAXIMUM_REPEATS}]"
        raise ValueError(message)
    harness_arguments(request.cycles, request.seed + repeats - 1)
    if output.exists():
        message = "output directory already exists"
        raise ValueError(message)
    if not request.harness.is_file():
        message = "harness binary is missing; run make closed-loop-harness"
        raise ValueError(message)
    output.mkdir()
    with ThreadPoolExecutor(max_workers=max(1, min(request.jobs, repeats))) as pool:
        entries = list(
            pool.map(
                lambda index: capture_repeat(
                    request.harness, output, index, request.cycles, request.seed + index - 1
                ),
                range(1, repeats + 1),
            )
        )
    document = {
        "schema": "loop-timing-witness.repeat-campaign.v1",
        "campaign_id": "closed-loop-campaign",
        "repeats": entries,
        "operator_notes": OPERATOR_NOTES,
    }
    path = output / "campaign.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Produce a closed-loop campaign or refuse with one line on standard error.

    Parameters
    ----------
    argv
        Command arguments; ``None`` reads the process arguments.

    Returns
    -------
    int
        Zero for a written campaign, one for a refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--harness", type=Path, default=DEFAULT_HARNESS)
    parser.add_argument("--jobs", type=int, default=build_jobs())
    args = parser.parse_args(argv)
    try:
        path = capture_campaign(
            CampaignRequest(
                args.output, args.cycles, args.repeats, args.seed, args.harness, args.jobs
            )
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"closed-loop run refused: {error}", file=sys.stderr)
        return 1
    print(f"closed-loop campaign: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
