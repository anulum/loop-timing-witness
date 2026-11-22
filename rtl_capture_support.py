# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real RTL captures and repeat campaigns for the tests

"""Produce real RTL captures, their run manifests and repeat campaigns for the analysis tests.

The capture RTL is copied into the run and simulated with Icarus Verilog, so the events are the
real binary records of the production capture. The tracking and power series beside them are
simulation data and cannot be cited as board measurements. A campaign orders copies of one
capture as numbered repeats, each a complete run with its own run ID.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

_REPOSITORY = Path(__file__).resolve().parent

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
        shutil.copyfile(_REPOSITORY / relative, destination)
    shutil.copyfile(_REPOSITORY / "measurement-domain.json", run / "measurement-domain.json")
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


def write_rtl_run(run: Path, profile: str) -> dict[str, Any]:
    """Create one run directory with real simulated events and its manifest.

    Parameters
    ----------
    run
        Run directory to create; its parent exists.
    profile
        Event profile of the capture.

    Returns
    -------
    dict[str, Any]
        The written manifest, a new mutable object.
    """
    run.mkdir()
    simulator_version = _simulate_events(run, profile)
    _write_series(run)
    manifest = _rtl_manifest(run, profile, simulator_version)
    (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


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


def write_repeat_campaign(
    campaign: Path,
    capture: tuple[Path, dict[str, Any]],
    repeats: int,
    run_plan: dict[str, int] | None,
) -> tuple[Path, dict[str, Any]]:
    """Create a campaign directory that orders copies of one capture as its repeats.

    Parameters
    ----------
    campaign
        Campaign directory to create, named ``campaign``; its parent exists.
    capture
        Original run directory and its manifest.
    repeats
        Number of repeats.
    run_plan
        Optional run-plan override for every repeat's measurement-domain copy.

    Returns
    -------
    tuple[Path, dict[str, Any]]
        The campaign manifest path and its document, a new mutable object.
    """
    campaign.mkdir()
    entries = [
        _repeat_entry(campaign / f"repeat-{index}", index, capture, run_plan)
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
