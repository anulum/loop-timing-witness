# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — legacy API consumers of actual runtime artifacts

"""Exercise repository API imports against real RTL, native and device-tree outputs."""

from __future__ import annotations

import copy
import json
import struct
import subprocess
import sys
from typing import TYPE_CHECKING

from amp_capture_observations import fault_schedule, tracking_csv
from amp_collisions import check_collisions
from amp_device import bind_device
from amp_report_completion import attach_amp_completion
from analyze_run import build_report
from device_tree_structure import decode_structure
from event_stream import decode_events
from native_completion import attach_completion_statistics
from run_manifest import load_run
from run_series import energy_per_cycle, tracking_error
from test_amp_device import PATH, SELECTION, SOURCE
from test_device_tree_interrupts import PLIC
from test_device_tree_resources import compile_tree
from test_native_run import configuration, native_run
from tracking_observations import observed_tracking_error

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from test_device_tree_resources import CompileTree

    from conftest import MakeRtlRun

__all__ = ["compile_tree", "native_run"]


def test_legacy_metrics_match_the_real_rtl_report(make_rtl_run: MakeRtlRun) -> None:
    """Consume hash-bound simulation records through the legacy public metric APIs.

    Parameters
    ----------
    make_rtl_run
        Actual Icarus fabric capture and complete source-bound analysis manifest.
    """
    run, manifest = make_rtl_run()
    inputs = load_run(run / "manifest.json")
    report, _ = build_report(inputs)
    contracts = inputs.domain["design_contracts"]
    events = decode_events(inputs.files["events"], contracts, "CONTROL", manifest["cycle_count"])
    tracking = tracking_error(
        inputs.files["tracking"], manifest["cycle_count"], 0, manifest["plant"]["tracking_unit"]
    )
    energy = energy_per_cycle(inputs.files["power"], events, "CONTROL", 0, contracts["power_rails"])
    assert all(report["tracking_error"][key] == value for key, value in tracking.items())
    assert all(report["energy"][key] == value for key, value in energy.items())
    before = copy.deepcopy(report)
    attach_completion_statistics(inputs, report, events)
    attach_amp_completion(inputs, report, events)
    assert report == before
    assert "native_completion" not in report
    assert "amp_completion" not in report


def test_legacy_topology_api_uses_actual_compiler_blocks(
    compile_tree: CompileTree, tmp_path: Path
) -> None:
    """Decode real DTB blocks and admit their declared non-colliding device resources.

    Parameters
    ----------
    compile_tree
        Actual device-tree compiler and public topology decoder.
    tmp_path
        Exclusive compiler output containing the original DTB.
    """
    tree = compile_tree(SOURCE)
    data = (tmp_path / "platform.dtb").read_bytes()
    header = struct.unpack_from(">10I", data)
    nodes = decode_structure(
        data[header[2] : header[2] + header[9]],
        data[header[3] : header[3] + header[8]],
    )
    assert nodes == tree.nodes
    device = bind_device(tree, PATH, SELECTION)
    check_collisions(tree, PATH, device.aperture, PLIC, 40)


def test_legacy_observations_preserve_actual_native_samples(
    native_run: Path, tmp_path: Path
) -> None:
    """Convert real controller observations without inventing cycles or fault schedules.

    Parameters
    ----------
    native_run
        Actual production RTL and controller executable for each plant.
    tmp_path
        Exclusive original configuration, raw tracking and event capture.
    """
    config = tmp_path / "configuration.txt"
    config.write_text(configuration("pid", "none"), encoding="ascii")
    event_path = tmp_path / "events.bin"
    raw_path = tmp_path / "tracking_raw.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(event_path), str(raw_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    domain = json.loads((REPOSITORY_ROOT / "measurement-domain.json").read_text())
    events = decode_events(event_path.read_bytes(), domain["design_contracts"], "CONTROL", 32)
    samples = sum(event.name == "SAMPLE_READ" for event in events)
    content = tracking_csv(raw_path.read_bytes(), 32, samples)
    metric = observed_tracking_error(content, events, 32, 0, "model_output")
    assert metric["status"] == "available"
    assert metric["sample_count"] == samples == 32
    assert metric["coverage_fraction"] == 1
    assert fault_schedule(config.read_bytes()) == []


def test_package_module_commands_analyse_real_rtl(make_rtl_run: MakeRtlRun) -> None:
    """Invoke both installed module commands against actual source-bound inputs.

    Parameters
    ----------
    make_rtl_run
        Actual Icarus event capture with hash-bound analysis inputs.
    """
    run, _ = make_rtl_run()
    report = run / "module-report"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "loop_timing_witness.analyze_run",
            str(run / "manifest.json"),
            "--output-dir",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((report / "report.json").read_text())["valid"] is True
    validation = subprocess.run(
        [sys.executable, "-m", "loop_timing_witness.validate_measurement_domain"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr
    assert "measurement-domain: PASS" in validation.stdout
