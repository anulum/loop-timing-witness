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

from loop_timing_witness.host_profile import scaled, verilator_jobs

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


_RTL_SOURCES = (
    "rtl/event_codes_pkg.sv",
    "rtl/event_record_capture.sv",
    "tests/rtl/event_capture_tb.sv",
)


_RTL_PLANT = {
    "name": "second_order_mechanical",
    "fixed_point_format": "Q16.16",
    "tracking_unit": "dimensionless",
}
_RTL_INSTRUMENT = {
    "fifo_overflow_count": 0,
    "floor_ticks": None,
    "known_period_pass": False,
    "injected_delay_pass": False,
    "overflow_pass": False,
    "bus_offset_pass": False,
}


def _reference(run: Path, relative: str) -> dict[str, str]:
    """Return the path and digest reference of one run file.

    Parameters
    ----------
    run
        Run directory.
    relative
        File path relative to the run.

    Returns
    -------
    dict[str, str]
        ``path`` and ``sha256`` of the file.
    """
    return {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}


def _simulate_events(run: Path, profile: str) -> str:
    """Copy the capture RTL, simulate one profile with Icarus Verilog and keep its events.

    Parameters
    ----------
    run
        New run directory.
    profile
        Event profile passed to the testbench.

    Returns
    -------
    str
        First line of the simulator's version report.
    """
    for relative in _RTL_SOURCES:
        destination = run / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, destination)
    shutil.copyfile(REPOSITORY_ROOT / "measurement-domain.json", run / "measurement-domain.json")
    simulation = run / "event_capture.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "event_capture_tb",
            "-o",
            str(simulation),
            *(str(run / relative) for relative in _RTL_SOURCES),
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
    return subprocess.run(
        ["iverilog", "-V"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]


def _write_series(run: Path) -> None:
    """Write the simulated tracking and four-rail power series of the run.

    Parameters
    ----------
    run
        Run directory.
    """
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


def _rtl_manifest(run: Path, profile: str, simulator_version: str) -> dict[str, Any]:
    """Return the run manifest of a simulated capture, in its written field order.

    Parameters
    ----------
    run
        Run directory holding every referenced file.
    profile
        Event profile; ``CONTROL`` adds the control declarations.
    simulator_version
        Simulator version line.

    Returns
    -------
    dict[str, Any]
        Manifest with the digest of every referenced file.
    """
    control = profile == "CONTROL"
    return {
        "schema": "loop-timing-witness.run-manifest.v1",
        "run_id": "rtl-capture-test",
        "started_utc": "2026-09-26T00:00:00Z",
        "source": {
            "kind": "rtl_simulation",
            "tool": "Icarus Verilog",
            "version": simulator_version,
            "files": [
                _reference(run, relative) for relative in (*_RTL_SOURCES, "event_capture.vvp")
            ],
        },
        "measurement_domain": _reference(run, "measurement-domain.json"),
        "profile": profile,
        "placement": "fabric_logic",
        "sample_period_ticks": 5000 if control else None,
        "cycle_count": 3 if control else 2,
        "warmup_cycles": 0,
        "load_case": "idle",
        "controller": {"name": "pid_anti_windup", "coefficients": {"kp": 1}} if control else None,
        "plant": dict(_RTL_PLANT) if control else None,
        "fault_schedule": [{"cycle": 2, "kind": "delay", "delay_periods": 1}] if control else [],
        "files": {
            "events": _reference(run, "events.bin"),
            "tracking": _reference(run, "tracking.csv") if control else None,
            "power": _reference(run, "power.csv"),
        },
        "hardware_artifacts": None,
        "instrument": dict(_RTL_INSTRUMENT),
        "environment": {"room_temperature_c": None, "board_supply_only": False},
        "operator_notes": "RTL simulation only",
    }


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
        simulator_version = _simulate_events(run, profile)
        _write_series(run)
        manifest = _rtl_manifest(run, profile, simulator_version)
        (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return run, manifest

    return make


MakeRepeatCampaign = Callable[..., tuple[Path, dict[str, Any]]]


def write_bound_json(path: Path, value: dict[str, Any]) -> dict[str, str]:
    """Write one JSON document and return its reference relative to the campaign.

    Parameters
    ----------
    path
        Destination two levels or one level below the campaign directory.
    value
        Document to serialise.

    Returns
    -------
    dict[str, str]
        Path relative to the campaign directory and SHA-256 of the written bytes.
    """
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    campaign = next(parent for parent in path.parents if parent.name == "campaign")
    return {
        "path": path.relative_to(campaign).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _repeat_entry(
    directory: Path,
    index: int,
    capture: tuple[Path, dict[str, Any]],
    run_plan: dict[str, int] | None,
) -> dict[str, Any]:
    """Copy one capture as a numbered repeat and return its campaign entry.

    Parameters
    ----------
    directory
        Repeat directory to create.
    index
        One-based repeat index, also the suffix of the repeat's run ID.
    capture
        Original run directory and its manifest.
    run_plan
        Optional run plan written into the repeat's measurement-domain copy,
        which the repeat manifest then binds.

    Returns
    -------
    dict[str, Any]
        Repeat index, bound repeat manifest and the reboot declaration.
    """
    run, manifest = capture
    shutil.copytree(run, directory)
    value = {**manifest, "run_id": f"rtl-repeat-{index}"}
    if run_plan is not None:
        domain = json.loads((directory / "measurement-domain.json").read_bytes())
        domain["design_contracts"]["run_plan"] = run_plan
        value["measurement_domain"] = {
            "path": "measurement-domain.json",
            "sha256": write_bound_json(directory / "measurement-domain.json", domain)["sha256"],
        }
    return {
        "repeat_index": index,
        "run_manifest": write_bound_json(directory / "manifest.json", value),
        "rebooted_before_run": True,
    }


@pytest.fixture
def make_repeat_campaign(tmp_path: Path, make_rtl_run: MakeRtlRun) -> MakeRepeatCampaign:
    """Order copies of one real RTL capture as the repeats of a campaign.

    Parameters
    ----------
    tmp_path
        Pytest scratch directory.
    make_rtl_run
        Production Icarus witness capture.

    Returns
    -------
    MakeRepeatCampaign
        Factory taking the repeat count, profile and an optional run-plan
        override for every repeat's measurement-domain copy. It returns the
        campaign manifest path and its mutable document. Each repeat is a
        complete run directory with a distinct run ID; the samples are
        simulation data.
    """

    def make(
        repeats: int = 5,
        profile: str = "CONTROL",
        run_plan: dict[str, int] | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        run, manifest = make_rtl_run(profile)
        campaign = tmp_path / "campaign"
        campaign.mkdir()
        entries = [
            _repeat_entry(campaign / f"repeat-{index}", index, (run, manifest), run_plan)
            for index in range(1, repeats + 1)
        ]
        document: dict[str, Any] = {
            "schema": "loop-timing-witness.repeat-campaign.v1",
            "campaign_id": "rtl-repeat-campaign",
            "repeats": entries,
            "operator_notes": "RTL simulation only",
        }
        path = campaign / "campaign.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path, document

    return make


RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


# Public-port RTL sources, in compilation order, compiled ahead of each testbench.
_PUBLIC_PORT_SOURCES = (
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
    "rtl/split_multiplier.sv",
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
)


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
        sources = [*_PUBLIC_PORT_SOURCES, f"tests/rtl/{top}.sv"]
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
            timeout=scaled(30),
        )
        return subprocess.run(
            ["vvp", str(simulation), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=scaled(60),
        )

    return run


@pytest.fixture(scope="session")
def closed_loop_harness(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the closed-loop benchmark harness once with the repository's Make target.

    Parameters
    ----------
    tmp_path_factory
        Session temporary directory factory.

    Returns
    -------
    Path
        Built harness executable in an owned directory.
    """
    directory = tmp_path_factory.mktemp("closed-loop-build")
    subprocess.run(
        [
            "make",
            "closed-loop-harness",
            f"CLOSED_LOOP_DIRECTORY={directory}",
            f"VERILATOR_JOBS={verilator_jobs()}",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        timeout=scaled(900),
    )
    return directory / "closed_loop_harness"


@pytest.fixture(scope="session")
def native_analysis_commands(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build both published native analysis commands and copy them into one directory.

    The executables are selected from Cargo's JSON messages, never by a build-directory path.

    Parameters
    ----------
    tmp_path_factory
        Session temporary directory factory.

    Returns
    -------
    Path
        Directory holding ``loop-timing-witness-analyze-native`` and
        ``loop-timing-witness-campaign-native``.
    """
    names = ("loop-timing-witness-analyze-native", "loop-timing-witness-campaign-native")
    result = subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--message-format=json",
            "--manifest-path",
            str(REPOSITORY_ROOT / "analysis/rust/Cargo.toml"),
            *(item for name in names for item in ("--bin", name)),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=scaled(1200),
        check=True,
    )
    built = {}
    for line in result.stdout.splitlines():
        message = json.loads(line) if line.startswith("{") else {}
        if message.get("reason") == "compiler-artifact" and message.get("executable"):
            built[message["target"]["name"]] = Path(message["executable"])
    directory = tmp_path_factory.mktemp("native-analysis")
    for name in names:
        shutil.copy2(built[name], directory / name)
    return directory
