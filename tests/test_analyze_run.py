# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host analysis command tests

"""Exercise the host CLI against a binary stream captured by real RTL simulation."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from analyze_run import main

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]


def test_undeclared_actual_fault_is_refused(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Refuse a valid manifest that omits a fault actually captured by production RTL.

    Parameters
    ----------
    make_rtl_run
        Real Icarus event producer retaining the injected fault and original hashes.
    run_tool
        Public host CLI process.
    tmp_path
        Exclusive report location that must remain absent after refusal.
    """
    run, manifest = make_rtl_run()
    assert manifest["fault_schedule"]
    manifest["fault_schedule"] = []
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "undeclared-fault-report"
    result = run_tool("analyze_run", str(path), "--output-dir", str(output))
    assert result.returncode == 1
    assert "fault schedule does not match captured FAULT_INJECTED events" in result.stderr
    assert not output.exists()


def test_control_run_from_rtl_simulation(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A simulated fault and late write reach every report artefact.

    Parameters
    ----------
    make_rtl_run
        Real Icarus Verilog event producer.
    run_tool
        Subprocess entry point for repository tools.
    tmp_path
        Output location.
    """
    run, manifest = make_rtl_run()
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["source_kind"] == "rtl_simulation"
    assert report["measurement_domain_sha256"] == manifest["measurement_domain"]["sha256"]
    assert report["input_sha256"]["measurement_domain"] == manifest["measurement_domain"]["sha256"]
    assert report["evidence_status"] == "simulation_only"
    assert report["valid"] is True
    assert report["events"]["event_count"] == 15
    assert report["events"]["control"]["deadline_misses"] == 1
    assert report["events"]["control"]["fault_detections"] == 1
    assert report["events"]["intervals"]["time_to_safe_state"]["maximum_ticks"] == 10
    assert report["tracking_error"]["sample_count"] == 3
    assert report["energy"]["sample_count"] == 3
    assert report["energy"]["per_rail"]["VDD"] == 0.1
    assert (output / "interval_summary.csv").is_file()
    assert (output / "cycle_intervals.csv").is_file()
    assert (output / "interval_p99.svg").is_file()
    assert (output / "energy_per_cycle.svg").is_file()
    assert "simulation_only" in (output / "interval_summary.csv").read_text(encoding="utf-8")
    assert "simulation_only" in (output / "interval_p99.svg").read_text(encoding="utf-8")


def test_report_directory_must_be_new(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A second run refuses to overwrite a finished report.

    Parameters
    ----------
    make_rtl_run
        Real Icarus Verilog event producer.
    run_tool
        Subprocess entry point for repository tools.
    tmp_path
        Output location.
    """
    run, _ = make_rtl_run()
    output = tmp_path / "report"
    first = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert first.returncode == 0, first.stderr
    original = (output / "report.json").read_bytes()
    second = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert second.returncode == 1
    assert "already exists" in second.stderr
    assert (output / "report.json").read_bytes() == original


def test_compute_profile_from_rtl_simulation(
    make_rtl_run: Callable[..., tuple[Path, dict[str, Any]]], run_tool: RunTool, tmp_path: Path
) -> None:
    """The five COMPUTE strobes decode without a fictional control plant.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog producer in COMPUTE mode.
    run_tool
        Host command runner.
    tmp_path
        Output location.
    """
    run, _ = make_rtl_run("COMPUTE")
    output = tmp_path / "compute-report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["valid"] is True
    assert report["profile"] == "COMPUTE"
    assert report["events"]["event_count"] == 10
    assert report["events"]["control"] is None
    assert report["events"]["intervals"]["compute_duration"]["median_ticks"] == 10
    assert report["tracking_error"]["status"] == "not_applicable"
    assert report["energy"]["sample_count"] == 2


def test_board_shaped_declaration_remains_unverified(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A board-shaped declaration cannot establish physical provenance.

    Parameters
    ----------
    make_rtl_run
        Known RTL simulation source, used to prove that a declaration alone
        cannot authenticate the physical source.
    run_tool
        Public host command runner.
    tmp_path
        Report parent.
    """
    run, manifest = make_rtl_run()
    manifest["source"]["kind"] = "board"
    reference = manifest["source"]["files"][0]
    manifest["hardware_artifacts"] = {
        name: reference.copy()
        for name in ("bitstream", "firmware", "linux_image", "controller_binary")
    }
    manifest["hardware_artifacts"].update(
        {"libero_version": "declaration-test", "toolchain_version": "declaration-test"}
    )
    manifest["instrument"].update(
        {
            "floor_ticks": 0,
            "known_period_pass": True,
            "injected_delay_pass": True,
            "overflow_pass": True,
            "bus_offset_pass": True,
        }
    )
    manifest["environment"] = {"room_temperature_c": 20, "board_supply_only": True}
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "declared-report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["source_kind"] == "board"
    assert report["evidence_status"] == "board_declaration_unverified"
    assert report["valid"] is True
    assert report["input_sha256"]["bitstream"] == reference["sha256"]


def test_imported_command_refuses_missing_manifest(tmp_path: Path) -> None:
    """The public command entry point reports a missing manifest without output.

    Parameters
    ----------
    tmp_path
        Path to a manifest that does not exist.
    """
    assert main([str(tmp_path / "absent.json"), "--output-dir", str(tmp_path / "report")]) == 1
    assert not (tmp_path / "report").exists()
