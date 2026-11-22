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
same way. The fixtures run tools as real subprocesses, create real Git work
trees, produce real RTL captures and campaigns through ``rtl_capture_support``,
run public-port RTL testbenches and build the native commands once a session.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from loop_timing_witness.host_profile import scaled, verilator_jobs
from rtl_capture_support import write_repeat_campaign, write_rtl_run

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
        Factory returning the run directory and its mutable manifest object, made by
        :func:`rtl_capture_support.write_rtl_run`. Input CSV files are simulation data and
        cannot be cited as board measurements.
    """

    def make(profile: str = "CONTROL") -> tuple[Path, dict[str, Any]]:
        run = tmp_path / "rtl-run"
        return run, write_rtl_run(run, profile)

    return make


MakeRepeatCampaign = Callable[..., tuple[Path, dict[str, Any]]]


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
        campaign manifest path and its mutable document, made by
        :func:`rtl_capture_support.write_repeat_campaign`. Each repeat is a
        complete run directory with a distinct run ID; the samples are
        simulation data.
    """

    def make(
        repeats: int = 5,
        profile: str = "CONTROL",
        run_plan: dict[str, int] | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        return write_repeat_campaign(
            tmp_path / "campaign", make_rtl_run(profile), repeats, run_plan
        )

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
