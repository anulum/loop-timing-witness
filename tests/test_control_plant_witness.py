# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — integrated plant witness simulations

"""Exercise plant trajectories, hardware faults and reports from drained RTL events."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import struct
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]
MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]


@pytest.mark.parametrize(
    "scenario", [(fault, thermal) for fault in [-1, 0, 1, 2, 3] for thermal in [0, 1]]
)
def test_integrated_plant_faults_and_host_reports(
    scenario: tuple[int, int],
    run_rtl: RunRtl,
    run_tool: RunTool,
    make_rtl_run: MakeRtlRun,
    tmp_path: Path,
) -> None:
    """Verify real trajectories and causal timestamps through the public analyzer.

    Parameters
    ----------
    scenario
        Fault kind and mechanical or thermal plant selection.
    run_rtl
        Public RTL compiler and simulator runner.
    run_tool
        Public CLI runner.
    make_rtl_run
        Simulation run manifest factory.
    tmp_path
        Bounded simulator and report directory.
    """
    fault, thermal = scenario
    run, manifest = make_rtl_run()
    mirrors = tmp_path / "mirrors.csv"
    stdout, rows = _simulate(run_rtl, run, fault, thermal, mirrors)
    check_trajectory(rows, thermal)
    _write_tracking(run, rows)
    _declare_plant(manifest, fault, thermal)
    _bind_sources(run, manifest, tmp_path / "control_plant_witness_tb.vvp")
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "reports"
    analysis = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert analysis.returncode == 0, analysis.stderr
    _check_plant_report(json.loads((output / "report.json").read_text(encoding="utf-8")), fault)
    if fault == 1:
        assert "delay=200000" in stdout
    events = list(struct.iter_unpack("<BBHIQ", (run / "events.bin").read_bytes()))
    assert [event[4] for event in events if event[0] == 4] == [
        int(rows[0]["ticks"]) + period * 100000 for period in range(1, 6)
    ]
    _check_mirrors(mirrors, events, fault)


def test_pps_reference_reaches_the_report(
    run_rtl: RunRtl,
    run_tool: RunTool,
    make_rtl_run: MakeRtlRun,
    tmp_path: Path,
) -> None:
    """Record a pulse beside the healthy run without changing any control record, then fit it.

    Every rise of the testbench pulse becomes one PPS record with the counter value two captures
    after the rise and consecutive sequence numbers; the control records equal those of the same
    run without the pulse, so the reference never displaces or delays them. The public analysis
    fits the simulated period exactly, which only checks the arithmetic: a simulated pulse has no
    physical second.

    Parameters
    ----------
    run_rtl
        Public RTL compiler and simulator runner.
    run_tool
        Public CLI runner.
    make_rtl_run
        Simulation run manifest factory.
    tmp_path
        Bounded simulator and report directory.
    """
    period = 110000
    run, manifest = make_rtl_run()
    rises_file = tmp_path / "pps.txt"
    result = run_rtl(
        "control_plant_witness_tb",
        {"FAULT": -1, "THERMAL": 0},
        [
            f"+EVENT_FILE={run / 'events.bin'}",
            f"+TRACK_FILE={run / 'plant.csv'}",
            f"+PPS_PERIOD={period}",
            f"+PPS_FILE={rises_file}",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROL_PASS records=25" in result.stdout
    plain = tmp_path / "plain"
    plain.mkdir()
    baseline = run_rtl(
        "control_plant_witness_tb",
        {"FAULT": -1, "THERMAL": 0},
        [f"+EVENT_FILE={plain / 'events.bin'}", f"+TRACK_FILE={plain / 'plant.csv'}"],
    )
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    events = list(struct.iter_unpack("<BBHIQ", (run / "events.bin").read_bytes()))
    rises = [int(line) for line in rises_file.read_text(encoding="utf-8").split()]
    assert rises == [1000 + period * second for second in range(5)]
    assert [event for event in events if event[0] == 18] == [
        (18, 0, 0, second, rise + 2) for second, rise in enumerate(rises)
    ]
    assert [event for event in events if event[0] != 18] == list(
        struct.iter_unpack("<BBHIQ", (plain / "events.bin").read_bytes())
    )
    with (run / "plant.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    _write_tracking(run, rows)
    _declare_plant(manifest, -1, 0)
    _bind_sources(run, manifest, tmp_path / "control_plant_witness_tb.vvp")
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "reports"
    analysis = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert analysis.returncode == 0, analysis.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    _check_plant_report(report, -1)
    assert report["events"]["event_count"] == 20
    assert report["reference_timebase"] == {
        "event": "PPS",
        "edges": 5,
        "first_sequence": 0,
        "last_sequence": 4,
        "missing_edges": 0,
        "ticks_per_second": float(period),
        "scale_error_ppm": (period - 100_000_000) / 100_000_000 * 1_000_000.0,
        "scale_standard_error_ppm": 0.0,
        "residual_rms_ticks": 0.0,
        "max_abs_residual_ticks": 0.0,
    }


def test_pps_edges_wait_for_free_slots_and_gaps_show_lost_edges(run_rtl: RunRtl) -> None:
    """Hold the drain until a pulse edge must wait and the next one is not recorded.

    The self-checking testbench also requires that a pulse already high at the reset's release
    is not an edge and that no reference loss counts as capture overflow.

    Parameters
    ----------
    run_rtl
        Public RTL compiler and simulator runner.
    """
    result = run_rtl("pps_reference_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PPS_PASS records=6" in result.stdout


def _check_mirrors(path: Path, events: list[tuple[int, ...]], fault: int) -> None:
    """Require each mirror edge on the edge that records its event.

    The two event mirrors toggle once per SAMPLE_READY and ACT_WRITE event, at the counter value
    the event's record carries; the safe-state mirror rises once, with SAFE_STATE, and stays high.

    Parameters
    ----------
    path
        Mirror changes written by the testbench, with the counter value of each edge.
    events
        Drained event records as ``(code, flags, reserved, cycle, ticks)``.
    fault
        Injected fault kind, or a negative value for none.
    """
    with path.open(encoding="utf-8", newline="") as stream:
        changes = [
            {name: int(value) for name, value in row.items()} for row in csv.DictReader(stream)
        ]
    levels = {"sample_ready": 0, "actuator_write": 0, "safe_state": 0}
    edges: dict[str, list[int]] = {name: [] for name in levels}
    for change in changes:
        for name, level in levels.items():
            if change[name] != level:
                edges[name].append(change["ticks"])
                levels[name] = change[name]
    assert edges["sample_ready"] == [event[4] for event in events if event[0] == 1]
    assert edges["actuator_write"] == [event[4] for event in events if event[0] == 3]
    assert edges["safe_state"] == [event[4] for event in events if event[0] == 5]
    assert len(edges["safe_state"]) == (0 if fault < 0 else 1)
    assert len(edges["sample_ready"]) == 5
    assert levels["safe_state"] == (0 if fault < 0 else 1)


def _simulate(
    run_rtl: RunRtl, run: Path, fault: int, thermal: int, mirrors: Path
) -> tuple[str, list[dict[str, str]]]:
    """Run the plant witness testbench into the run directory and read its plant rows.

    Parameters
    ----------
    run_rtl
        Public RTL compiler and simulator runner.
    run
        Run directory receiving ``events.bin`` and ``plant.csv``.
    fault
        Injected fault kind, or a negative value for none.
    thermal
        Mechanical (0) or thermal (1) plant.
    mirrors
        File receiving the mirror changes.

    Returns
    -------
    tuple[str, list[dict[str, str]]]
        Simulator output, which reports both passes, and the five plant rows.
    """
    raw_tracking = run / "plant.csv"
    result = run_rtl(
        "control_plant_witness_tb",
        {"FAULT": fault, "THERMAL": thermal},
        [
            f"+EVENT_FILE={run / 'events.bin'}",
            f"+TRACK_FILE={raw_tracking}",
            f"+MIRROR_FILE={mirrors}",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROL_PASS" in result.stdout
    assert "RESET_PASS" in result.stdout
    with raw_tracking.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 5
    return result.stdout, rows


def _write_tracking(run: Path, rows: list[dict[str, str]]) -> None:
    """Write the plant's reference and output as the run's tracking series.

    Parameters
    ----------
    run
        Run directory.
    rows
        Plant rows in Q8.24.
    """
    (run / "tracking.csv").write_text(
        "cycle,reference,output\n"
        + "".join(
            f"{row['cycle']},{int(row['reference']) / (1 << 24)},{int(row['output']) / (1 << 24)}\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _declare_plant(manifest: dict[str, Any], fault: int, thermal: int) -> None:
    """Declare the five-cycle plant run and its fault schedule.

    Parameters
    ----------
    manifest
        Declaration changed in place.
    fault
        Injected fault kind at cycle 1, or a negative value for none.
    thermal
        Mechanical (0) or thermal (1) plant.
    """
    # Energy is unavailable: no power-monitor hardware is present in simulation.
    manifest["files"]["power"] = None
    manifest["cycle_count"] = 5
    manifest["sample_period_ticks"] = 100000
    manifest["plant"]["fixed_point_format"] = "Q8.24"
    manifest["plant"]["name"] = "first_order_thermal" if thermal else "second_order_mechanical"
    manifest["fault_schedule"] = (
        [
            {
                "cycle": 1,
                "kind": ["drop", "delay", "freeze", "overload_request"][fault],
                "delay_periods": 2 if fault == 1 else 0,
            }
        ]
        if fault >= 0
        else []
    )


def _bind_sources(run: Path, manifest: dict[str, Any], simulation: Path) -> None:
    """Copy every RTL source, the testbench and its simulation into the run and bind them.

    Parameters
    ----------
    run
        Run directory holding the plant series.
    manifest
        Declaration changed in place.
    simulation
        Compiled testbench.
    """
    repository = Path(__file__).resolve().parents[1]
    sources = [
        str(path.relative_to(repository)) for path in sorted((repository / "rtl").glob("*.sv"))
    ]
    sources += ["tests/rtl/control_plant_witness_tb.sv"]
    for relative in sources:
        destination = run / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, destination)
    shutil.copyfile(simulation, run / "control_plant_witness_tb.vvp")
    manifest["source"]["files"] = [
        {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}
        for relative in [*sources, "control_plant_witness_tb.vvp", "plant.csv"]
    ]
    for name in ("events", "tracking"):
        manifest["files"][name]["sha256"] = hashlib.sha256(
            (run / manifest["files"][name]["path"]).read_bytes()
        ).hexdigest()


def _check_plant_report(report: dict[str, Any], fault: int) -> None:
    """Require the analysed plant run's faults, misses and latencies.

    Parameters
    ----------
    report
        Published analysis report.
    fault
        Injected fault kind, or a negative value for none.
    """
    assert report["evidence_status"] == "simulation_only"
    assert report["fifo_overflow_count"] == 0
    assert report["events"]["control"]["fault_injections"] == (0 if fault < 0 else 1)
    assert report["events"]["control"]["safe_state_events"] == (0 if fault < 0 else 1)
    assert report["events"]["control"]["deadline_misses"] == (0 if fault < 0 else 4)
    assert report["events"]["intervals"]["loop_latency"]["maximum_ticks"] == 20
    if fault == 1:
        assert report["events"]["intervals"]["fault_detection"]["maximum_ticks"] == 200000
        assert report["events"]["intervals"]["time_to_safe_state"]["maximum_ticks"] == 100000


def test_boundary_write_is_late(
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Count an exact-deadline command and preserve its new-cycle event timestamp.

    Parameters
    ----------
    run_rtl
        Public RTL simulation runner.
    tmp_path
        Binary event and trajectory directory.
    """
    events = tmp_path / "events.bin"
    result = run_rtl(
        "control_plant_witness_tb",
        {"BOUNDARY_WRITE": 1},
        [f"+EVENT_FILE={events}", f"+TRACK_FILE={tmp_path / 'plant.csv'}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "late=3" in result.stdout
    decoded = list(struct.iter_unpack("<BBHIQ", events.read_bytes()))
    late = [event for event in decoded if event[0] == 13]
    assert len(late) == 1
    assert late[0][3] == 1
    assert late[0][4] == next(event[4] for event in decoded if event[0] == 4)
    assert not any(event[0] == 3 for event in decoded)


def check_trajectory(rows: list[dict[str, str]], thermal: int) -> None:
    """Compare observed state transitions with exact integer multiply-add arithmetic.

    Parameters
    ----------
    rows
        Public sample, velocity and applied-actuator values from the RTL run.
    thermal
        Selected plant model.
    """
    position = velocity = 0
    for row in rows:
        actuator = int(row["actuator"])
        if thermal:
            position = (16760447 * position + 16769 * actuator) >> 24
        else:
            position, velocity = (
                (16777208 * position + 16769 * velocity + 8 * actuator) >> 24,
                (-16769 * position + 16760439 * velocity + 16769 * actuator) >> 24,
            )
        assert int(row["output"]) == position
        assert int(row["velocity"]) == velocity
        assert int(row["reference"]) == 1 << 24
    if all(int(row["actuator"]) == 1 << 24 for row in rows[1:]):
        elapsed = 0.004
        if thermal:
            continuous = 1 - math.exp(-elapsed)
        else:
            beta = math.sqrt(0.75)
            continuous = 1 - math.exp(-elapsed / 2) * (
                math.cos(beta * elapsed) + math.sin(beta * elapsed) / (2 * beta)
            )
        assert abs(position / (1 << 24) - continuous) < 64 / (1 << 24)


@pytest.mark.parametrize("thermal", [0, 1])
def test_signed_actuator_trajectory(
    thermal: int,
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Apply signed actuator changes and compare the actual plant trajectories.

    Parameters
    ----------
    thermal
        Selected physical plant.
    run_rtl
        Public RTL simulation runner.
    tmp_path
        Run output directory.
    """
    tracking = tmp_path / "plant.csv"
    result = run_rtl(
        "control_plant_witness_tb",
        {"SIGNED_COMMAND": 1, "THERMAL": thermal},
        [f"+EVENT_FILE={tmp_path / 'events.bin'}", f"+TRACK_FILE={tracking}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with tracking.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    check_trajectory(rows, thermal)
    assert [int(row["actuator"]) for row in rows] == [0, 33554432, -16777216, 8388608, -33554432]
