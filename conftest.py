# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared test configuration

"""Shared test configuration.

The stand-alone modules under ``tools/`` run as ``python tools/<name>.py``,
which puts ``tools/`` first on the import path; the tests import them the
same way. The fixtures run tools as real subprocesses and create real Git
work trees.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("controller_test_support",)

REPOSITORY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY_ROOT / "tools"))

RunTool = Callable[..., subprocess.CompletedProcess[str]]
MakeGitTree = Callable[[dict[str, str | bytes]], Path]
MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]


@pytest.fixture
def run_tool() -> RunTool:
    """Return a runner that executes one repository tool as a subprocess.

    Returns
    -------
    RunTool
        ``run(tool_name, *arguments)`` runs ``python tools/<tool_name>.py``
        from the repository root with the current interpreter and returns the
        completed process with captured text output.
    """

    def run(tool: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "tools" / f"{tool}.py"), *arguments],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    return run


@pytest.fixture
def make_git_tree(tmp_path: Path) -> MakeGitTree:
    """Return a factory for Git work trees populated with given files.

    Parameters
    ----------
    tmp_path
        Pytest-provided scratch directory.

    Returns
    -------
    MakeGitTree
        ``make(files)`` initialises a Git repository in a new directory,
        writes each relative path with its text or bytes, and returns the
        work-tree root. Nothing is staged or committed.
    """
    counter = 0

    def make(files: dict[str, str | bytes]) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"tree-{counter}"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        return root

    return make


@pytest.fixture
def make_rtl_run(tmp_path: Path) -> MakeRtlRun:
    """Produce real binary events with Icarus Verilog and a simulation manifest.

    Parameters
    ----------
    tmp_path
        Pytest scratch directory.

    Returns
    -------
    MakeRtlRun
        Factory returning the run directory and its mutable manifest object.
        Input CSV files are simulation data and cannot be cited as board
        measurements.
    """

    def make(profile: str = "CONTROL") -> tuple[Path, dict[str, Any]]:
        run = tmp_path / "rtl-run"
        run.mkdir()
        sources = (
            "rtl/event_codes_pkg.sv",
            "rtl/event_record_capture.sv",
            "tests/rtl/event_capture_tb.sv",
        )
        for relative in sources:
            destination = run / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY_ROOT / relative, destination)
        shutil.copyfile(
            REPOSITORY_ROOT / "measurement-domain.json", run / "measurement-domain.json"
        )
        simulation = run / "event_capture.vvp"
        subprocess.run(
            [
                "iverilog",
                "-g2012",
                "-s",
                "event_capture_tb",
                "-o",
                str(simulation),
                *(str(run / relative) for relative in sources),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["vvp", str(simulation), f"+EVENT_FILE={run / 'events.bin'}", f"+PROFILE={profile}"],
            check=True,
            capture_output=True,
            text=True,
        )
        simulator_version = subprocess.run(
            ["iverilog", "-V"], check=True, capture_output=True, text=True
        ).stdout.splitlines()[0]
        (run / "tracking.csv").write_text(
            "cycle,reference,output\n0,1,0.9\n1,2,1.8\n2,3,2.7\n", encoding="utf-8"
        )
        (run / "power.csv").write_text(
            "timebase_ticks,rail,voltage_v,current_a,energy_j\n"
            "0,VDD,1,0.1,0\n0,VDD25,2.5,0.1,0\n0,VDDA25,2.5,0.1,0\n0,VDDA,1,0.1,0\n"
            "15021,VDD,1,0.1,0.3\n15021,VDD25,2.5,0.1,0.6\n"
            "15021,VDDA25,2.5,0.1,0.9\n15021,VDDA,1,0.1,1.2\n",
            encoding="utf-8",
        )

        def reference(relative: str) -> dict[str, str]:
            return {
                "path": relative,
                "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest(),
            }

        manifest: dict[str, Any] = {
            "schema": "loop-timing-witness.run-manifest.v1",
            "run_id": "rtl-capture-test",
            "started_utc": "2026-09-26T00:00:00Z",
            "source": {
                "kind": "rtl_simulation",
                "tool": "Icarus Verilog",
                "version": simulator_version,
                "files": [reference(relative) for relative in (*sources, "event_capture.vvp")],
            },
            "measurement_domain": reference("measurement-domain.json"),
            "profile": profile,
            "placement": "fabric_logic",
            "sample_period_ticks": 5000 if profile == "CONTROL" else None,
            "cycle_count": 3 if profile == "CONTROL" else 2,
            "warmup_cycles": 0,
            "load_case": "idle",
            "controller": {"name": "pid_anti_windup", "coefficients": {"kp": 1}}
            if profile == "CONTROL"
            else None,
            "plant": {
                "name": "second_order_mechanical",
                "fixed_point_format": "Q16.16",
                "tracking_unit": "dimensionless",
            }
            if profile == "CONTROL"
            else None,
            "fault_schedule": [{"cycle": 2, "kind": "delay", "delay_periods": 1}]
            if profile == "CONTROL"
            else [],
            "files": {
                "events": reference("events.bin"),
                "tracking": reference("tracking.csv") if profile == "CONTROL" else None,
                "power": reference("power.csv"),
            },
            "hardware_artifacts": None,
            "instrument": {
                "fifo_overflow_count": 0,
                "floor_ticks": None,
                "known_period_pass": False,
                "injected_delay_pass": False,
                "overflow_pass": False,
                "bus_offset_pass": False,
            },
            "environment": {"room_temperature_c": None, "board_supply_only": False},
            "operator_notes": "RTL simulation only",
        }
        (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return run, manifest

    return make


RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.fixture
def run_rtl(tmp_path: Path) -> RunRtl:
    """Compile and execute a public-port RTL testbench with a bounded lifetime.

    Parameters
    ----------
    tmp_path
        Pytest scratch directory for compiled simulation files.

    Returns
    -------
    RunRtl
        Runner taking a testbench name, integer parameter overrides and vvp
        arguments. Compilation failure propagates; simulation output and exit
        status are returned for behavioural assertions.
    """

    def run(
        top: str, parameters: dict[str, int], arguments: list[str]
    ) -> subprocess.CompletedProcess[str]:
        simulation = tmp_path / f"{top}.vvp"
        sources = [
            "rtl/event_codes_pkg.sv",
            "rtl/clock_reset_release.sv",
            "rtl/clock_request_bridge.sv",
            "rtl/axi_lite_clock_bridge.sv",
            "rtl/event_record_window.sv",
            "rtl/control_io_registers.sv",
            "rtl/run_configuration_registers.sv",
            "rtl/axi_control_witness.sv",
            "rtl/icicle_witness.sv",
            "rtl/run_reset_control.sv",
            "rtl/retained_interrupt.sv",
            "rtl/event_record_capture.sv",
            "rtl/event_record_fifo.sv",
            "rtl/event_witness.sv",
            "rtl/fixed_point_math.sv",
            "rtl/fixed_point_controller.sv",
            "rtl/sampled_plant.sv",
            "rtl/reference_generator.sv",
            "rtl/deadline_monitor.sv",
            "rtl/fault_injector.sv",
            "rtl/control_event_capture.sv",
            "rtl/control_cycle.sv",
            "rtl/control_plant_witness.sv",
            "rtl/fabric_control_witness.sv",
            f"tests/rtl/{top}.sv",
        ]
        subprocess.run(
            [
                "iverilog",
                "-g2012",
                "-s",
                top,
                "-o",
                str(simulation),
                *(f"-P{top}.{name}={value}" for name, value in parameters.items()),
                *(str(REPOSITORY_ROOT / source) for source in sources),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return subprocess.run(
            ["vvp", str(simulation), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    return run
