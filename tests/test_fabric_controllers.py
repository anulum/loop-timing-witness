# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — closed-loop controller native parity and drained host reports

"""Exercise actual fabric feedback and verify native commands against its states."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
from test_controller_parity import DEFAULT, SCALE

from conftest import REPOSITORY_ROOT, MakeRtlRun, RunRtl, RunTool

if TYPE_CHECKING:
    from pathlib import Path

COEFFICIENT_NAMES = (
    "kp",
    "ki_period",
    "derivative_decay",
    "derivative_gain",
    "position_gain",
    "velocity_gain",
    "reference_gain",
    "output_min",
    "output_max",
    "integral_min",
    "integral_max",
)


@pytest.mark.parametrize("scenario", [(thermal, lqr) for thermal in [0, 1] for lqr in [0, 1]])
def test_feedback_native_parity_and_host_report(
    scenario: tuple[int, int],
    native_controllers: tuple[Path, Path],
    run_rtl: RunRtl,
    run_tool: RunTool,
    make_rtl_run: MakeRtlRun,
) -> None:
    """Close the real RTL feedback loop and bind its binary drain to host analysis.

    Parameters
    ----------
    scenario
        Mechanical/thermal model and PID/discrete LQR selection.
    native_controllers
        Public C and Rust executables.
    run_rtl
        Real public-port fabric simulation.
    run_tool
        Host command entry point.
    make_rtl_run
        Real run-package factory.
    """
    thermal, lqr = scenario
    run, manifest = make_rtl_run()
    result = run_rtl(
        "fabric_control_witness_tb",
        {"THERMAL": thermal, "LQR": lqr},
        [
            f"+EVENT_FILE={run / 'events.bin'}",
            f"+TRACK_FILE={run / 'plant.csv'}",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    shutil.copyfile(
        run.parent / "fabric_control_witness_tb.vvp", run / "fabric_control_witness_tb.vvp"
    )
    with (run / "plant.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 5
    coefficients = _coefficients(thermal)
    outputs = _native_commands(native_controllers, "lqr" if lqr else "pid", coefficients, rows)
    commands = [int(line.split(",")[1]) for line in outputs[0].splitlines()]
    assert [int(row["actuator"]) for row in rows] == [0, *commands[:-1]]
    _write_tracking(run, rows)
    _declare_fabric(manifest, thermal, lqr, coefficients)
    _bind_sources(run, manifest)
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    _check_fabric_report(run, run_tool)
    check_native_replays(run, thermal, (native_controllers, outputs), run_rtl, run_tool)


def _coefficients(thermal: int) -> tuple[int, ...]:
    """Return the public fabric default coefficients of one plant model.

    Parameters
    ----------
    thermal
        Mechanical (0) or thermal (1) model.

    Returns
    -------
    tuple[int, ...]
        Raw coefficient row in Q8.24.
    """
    gains = (6944437, 0, 23721653) if thermal else (38822697, 26419076, 55599913)
    coefficients = (*DEFAULT[:4], *gains, *DEFAULT[7:])
    # The public fabric default rounds Ki*T to nearest, rather than truncating.
    return (coefficients[0], 16777, *coefficients[2:])


def _native_commands(
    binaries: tuple[Path, Path],
    mode: str,
    coefficients: tuple[int, ...],
    rows: list[dict[str, str]],
) -> list[str]:
    """Run both native controllers on the fabric's samples and require equal commands.

    Parameters
    ----------
    binaries
        Public C and Rust executables.
    mode
        ``pid`` or ``lqr``.
    coefficients
        Raw coefficient row.
    rows
        Fabric plant rows.

    Returns
    -------
    list[str]
        Each executable's command stream.
    """
    payload = (
        ",".join(map(str, coefficients))
        + "\n"
        + "".join(
            f"{row['cycle']},{row['reference']},{row['output']},{row['velocity']}\n" for row in rows
        )
    )
    outputs = []
    for binary in binaries:
        native = subprocess.run(
            [str(binary), mode], input=payload, capture_output=True, text=True, check=False
        )
        assert native.returncode == 0, native.stderr
        outputs.append(native.stdout)
    assert outputs[0] == outputs[1]
    return outputs


def _write_tracking(run: Path, rows: list[dict[str, str]]) -> None:
    """Write the fabric's reference and output as the run's tracking series.

    Parameters
    ----------
    run
        Run directory.
    rows
        Fabric plant rows in Q8.24.
    """
    (run / "tracking.csv").write_text(
        "cycle,reference,output\n"
        + "".join(
            f"{row['cycle']},{int(row['reference']) / SCALE},{int(row['output']) / SCALE}\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _declare_fabric(
    manifest: dict[str, Any], thermal: int, lqr: int, coefficients: tuple[int, ...]
) -> None:
    """Declare the five-cycle fabric run, its plant and its controller.

    Parameters
    ----------
    manifest
        Declaration changed in place.
    thermal
        Mechanical (0) or thermal (1) model.
    lqr
        PID (0) or discrete LQR (1).
    coefficients
        Raw coefficient row.
    """
    manifest["files"]["power"] = None
    manifest["cycle_count"] = 5
    manifest["sample_period_ticks"] = 100000
    manifest["fault_schedule"] = []
    manifest["plant"]["name"] = "first_order_thermal" if thermal else "second_order_mechanical"
    manifest["plant"]["fixed_point_format"] = "Q8.24"
    manifest["controller"] = {
        "name": "discrete_lqr" if lqr else "pid_anti_windup",
        "coefficients": dict(zip(COEFFICIENT_NAMES, coefficients, strict=True)),
    }


def _bind_sources(run: Path, manifest: dict[str, Any]) -> None:
    """Copy every RTL source and the testbench into the run and bind them and the series.

    Parameters
    ----------
    run
        Run directory holding the compiled simulation and the plant series.
    manifest
        Declaration changed in place.
    """
    sources = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in sorted((REPOSITORY_ROOT / "rtl").glob("*.sv"))
    ]
    sources += ["tests/rtl/fabric_control_witness_tb.sv"]
    for relative in sources:
        destination = run / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, destination)
    manifest["source"]["files"] = [
        {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}
        for relative in [*sources, "fabric_control_witness_tb.vvp", "plant.csv"]
    ]
    for name in ("events", "tracking"):
        manifest["files"][name]["sha256"] = hashlib.sha256(
            (run / manifest["files"][name]["path"]).read_bytes()
        ).hexdigest()


def _check_fabric_report(run: Path, run_tool: RunTool) -> None:
    """Analyse the fabric run through the public command and require its timing.

    Parameters
    ----------
    run
        Bound fabric run package.
    run_tool
        Host command entry point.
    """
    output = run / "reports"
    analysis = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert analysis.returncode == 0, analysis.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["evidence_status"] == "simulation_only"
    assert report["fifo_overflow_count"] == 0
    assert report["events"]["control"]["deadline_misses"] == 0
    assert report["events"]["intervals"]["scheduling_latency"]["maximum_ticks"] == 1
    assert report["events"]["intervals"]["compute_time"]["maximum_ticks"] == 1
    assert report["events"]["intervals"]["loop_latency"]["maximum_ticks"] == 2


def check_native_replays(
    run: Path,
    thermal: int,
    programs_and_commands: tuple[tuple[Path, Path], list[str]],
    run_rtl: RunRtl,
    run_tool: RunTool,
) -> None:
    """Replay native commands through the real actuator and drained host analyzer.

    Parameters
    ----------
    run
        Original fabric run package, containing its manifest and host report.
    thermal
        Same mechanical/thermal model selection as the original run.
    programs_and_commands
        Public native executable paths and their actual generated command streams.
    run_rtl
        Actual public-port simulation runner.
    run_tool
        Host analyzer CLI runner.
    """
    native_controllers, outputs = programs_and_commands
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((run / "reports/report.json").read_text(encoding="utf-8"))
    # Drive actual native-produced commands through the public external actuator port.
    # This is deterministic lockstep replay, not measured processor/bus execution.
    for index, commands_text in enumerate(outputs):
        prefix = f"native-{index}"
        command_file = run / f"{prefix}-commands.csv"
        command_file.write_text(commands_text, encoding="utf-8")
        _replay_rtl(run_rtl, run, thermal, prefix)
        simulator = f"{prefix}-replay.vvp"
        shutil.copyfile(run.parent / "fabric_control_witness_tb.vvp", run / simulator)
        native_binary = f"{prefix}-controller"
        shutil.copyfile(native_controllers[index], run / native_binary)
        replay_path = run / f"{prefix}-manifest.json"
        replay_path.write_text(
            json.dumps(_replay_manifest(run, manifest, prefix, command_file.name)) + "\n",
            encoding="utf-8",
        )
        replay_report = run / f"{prefix}-report"
        analysis = run_tool("analyze_run", str(replay_path), "--output-dir", str(replay_report))
        assert analysis.returncode == 0, analysis.stderr
        native_report = json.loads((replay_report / "report.json").read_text(encoding="utf-8"))
        assert native_report["evidence_status"] == "simulation_only"
        assert native_report["events"] == report["events"]


def _replay_rtl(run_rtl: RunRtl, run: Path, thermal: int, prefix: str) -> None:
    """Drive one replay's commands through the external actuator port and require the original run.

    Parameters
    ----------
    run_rtl
        Actual public-port simulation runner.
    run
        Run package holding ``<prefix>-commands.csv``.
    thermal
        Same mechanical/thermal model selection as the original run.
    prefix
        Replay file prefix.
    """
    replay = run_rtl(
        "fabric_control_witness_tb",
        {"THERMAL": thermal, "EXTERNAL": 1},
        [
            f"+EVENT_FILE={run / f'{prefix}-events.bin'}",
            f"+TRACK_FILE={run / f'{prefix}-plant.csv'}",
            f"+COMMAND_FILE={run / f'{prefix}-commands.csv'}",
        ],
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert (run / f"{prefix}-plant.csv").read_bytes() == (run / "plant.csv").read_bytes()
    assert (run / f"{prefix}-events.bin").read_bytes() == (run / "events.bin").read_bytes()


def _replay_manifest(
    run: Path, manifest: dict[str, Any], prefix: str, command_file: str
) -> dict[str, Any]:
    """Return the declaration of one native command replay, bound to its own files.

    Parameters
    ----------
    run
        Run package holding the replay's files.
    manifest
        Original fabric run declaration, left unchanged.
    prefix
        Replay file prefix.
    command_file
        Replayed command file name.

    Returns
    -------
    dict[str, Any]
        Replay declaration: user-space placement, its events and the added sources.
    """
    replay_manifest: dict[str, Any] = json.loads(json.dumps(manifest))
    replay_manifest["placement"] = "linux_user_space"
    replay_manifest["operator_notes"] = (
        "Host-native command replay into RTL; deterministic two-tick simulated service. "
        "No U54, UIO, real-time scheduler, bus latency, physical board or power measurement."
    )
    replay_manifest["files"]["events"] = {
        "path": f"{prefix}-events.bin",
        "sha256": hashlib.sha256((run / f"{prefix}-events.bin").read_bytes()).hexdigest(),
    }
    added = [f"{prefix}-replay.vvp", f"{prefix}-controller", command_file, f"{prefix}-plant.csv"]
    replay_manifest["source"]["files"] += [
        {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}
        for relative in added
    ]
    return replay_manifest
