# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native source snapshot and report integration

"""Capture actual native RTL runs through the public producer and host analyzer."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from capture_native_simulation import CaptureOptions, capture_simulation
from test_native_run import configuration

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool


@pytest.mark.parametrize(
    "scenario",
    [(0, "none"), (1, "none"), (0, "drop"), (1, "delay"), (1, "freeze"), (0, "overload")],
)
def test_real_capture(scenario: tuple[int, str], tmp_path: Path, run_tool: RunTool) -> None:
    """Bind actual native configuration, source, executable, observations and reports.

    Parameters
    ----------
    scenario
        Actual compiled plant and injected RTL fault.
    tmp_path
        Exclusive capture allocation.
    run_tool
        Public repository command runner.
    """
    thermal, fault = scenario
    config = tmp_path / "configuration.txt"
    config.write_text(configuration("lqr" if thermal else "pid", fault), encoding="utf-8")
    run = tmp_path / "capture"
    policy_options = ["--cpu", str(min(os.sched_getaffinity(0))), "--scheduler", "normal"]
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(run),
        "--thermal",
        str(thermal),
        *policy_options,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((run / "manifest.json").read_text())
    metadata = json.loads((run / "native_metadata.json").read_text())
    report = json.loads((run / "reports/report.json").read_text())
    assert metadata["thermal"] == bool(thermal)
    assert metadata["host_policy"]["affinity_cpus"] == [min(os.sched_getaffinity(0))]
    assert metadata["host_policy"]["scheduler"] == os.SCHED_OTHER
    assert metadata["fault"]["kind"] == ("overload_request" if fault == "overload" else fault)
    assert manifest["tracking_sampling"] == "observed"
    assert manifest["files"]["power"] is None
    assert "source/runtime/isa/spike_plugin.mk" in {
        reference["path"] for reference in manifest["source"]["files"]
    }
    assert report["evidence_status"] == "simulation_only"
    assert report["events"]["control"]["observed_deadlines"] == 32
    assert report["tracking_error"]["sample_count"] == metadata["result"]["samples"]
    assert report["tracking_error"]["status"] == ("available" if fault == "none" else "partial")
    assert report["valid"] is False
    assert report["energy"]["status"] == "unavailable"
    for reference in manifest["source"]["files"]:
        assert (
            hashlib.sha256((run / reference["path"]).read_bytes()).hexdigest()
            == reference["sha256"]
        )
    repeat = run_tool("capture_native_simulation", str(config), "--output-dir", str(run))
    assert repeat.returncode == 1
    assert json.loads((run / "manifest.json").read_text()) == manifest
    analysis = run_tool(
        "analyze_run", str(run / "manifest.json"), "--output-dir", str(run / "reanalysis")
    )
    assert analysis.returncode == 0, analysis.stdout + analysis.stderr
    assert json.loads((run / "reanalysis/report.json").read_text()) == report


@pytest.mark.parametrize(("thermal", "fifo_bits"), [(-1, 8), (2, 8), (0, 0), (0, 15)])
def test_invalid_build_parameters(tmp_path: Path, thermal: int, fifo_bits: int) -> None:
    """Refuse invalid public API build modes before allocating capture artifacts.

    Parameters
    ----------
    tmp_path
        Exclusive capture allocation.
    thermal
        Requested plant mode.
    fifo_bits
        Requested FIFO address width.
    """
    output = tmp_path / "capture"
    with pytest.raises(ValueError, match=r"thermal|FIFO"):
        capture_simulation(
            tmp_path / "absent.conf", output, thermal, options=CaptureOptions(fifo_bits)
        )
    assert not output.exists()


def test_native_summary_write_failure(tmp_path: Path) -> None:
    """Retain real completed artifacts but refuse a run whose summary cannot be written.

    Parameters
    ----------
    tmp_path
        Exclusive source snapshot and actual failing output sink.
    """
    config = tmp_path / "configuration.txt"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    output = tmp_path / "capture"
    with ThreadPoolExecutor(max_workers=1) as executor:
        capture = executor.submit(capture_simulation, config, output, 0)
        limit = time.monotonic() + 30
        while not (output / "build.log").exists() and not capture.done():
            if time.monotonic() >= limit:
                pytest.fail("actual source snapshot did not reach compilation")
            time.sleep(0.01)
        (output / "native.log").symlink_to("/dev/full")
        with pytest.raises(subprocess.CalledProcessError):
            capture.result(timeout=120)
    metadata = json.loads((output / "native_metadata.json").read_text())
    assert metadata["result"]["samples"] == 32
    assert metadata["result"]["overflow"] == 0
    assert (output / "events.bin").stat().st_size > 0
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("fault", ["none", "overload"])
def test_actual_fifo_loss(tmp_path: Path, run_tool: RunTool, fault: str) -> None:
    """Retain an invalid report after actual two-record FIFO losses and live counts.

    Parameters
    ----------
    tmp_path
        Exclusive source-bound capture allocation.
    run_tool
        Actual public producer and analyzer subprocesses.
    fault
        Healthy control or real overload work with explicit model-time stall.
    """
    config = tmp_path / "configuration.txt"
    text = configuration("pid", fault)
    if fault == "overload":
        text = text.replace("1000 1100000", "1000 10000000")
    config.write_text(text, encoding="utf-8")
    run = tmp_path / "capture"
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(run),
        "--fifo-address-bits",
        "1",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "INVALID: FIFO overflow" in result.stderr
    native = json.loads((run / "native_metadata.json").read_text())
    report = json.loads((run / "reports/report.json").read_text())
    assert native["result"]["overflow"] > 0
    assert report["native_completion"] == native["result"]
    assert report["fifo_overflow_count"] == native["result"]["overflow"]
    assert report["events"]["event_count"] == native["result"]["records"]
    assert report["valid"] is False
    assert "event FIFO overflow" in report["invalid_reasons"]
    assert report["evidence_status"] == "simulation_only"
    assert report["events"]["control"]["deadline_misses"] != native["result"]["misses"]
    assert json.loads((run / "build_parameters.json").read_text())["fifo_address_bits"] == 1
    reanalysis = run_tool(
        "analyze_run", str(run / "manifest.json"), "--output-dir", str(run / "reanalysis")
    )
    assert reanalysis.returncode == 0, reanalysis.stdout + reanalysis.stderr
    assert json.loads((run / "reanalysis/report.json").read_text()) == report
    if fault == "overload":
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["warmup_cycles"] = 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        post_warmup = run_tool(
            "analyze_run", str(manifest_path), "--output-dir", str(run / "post_warmup")
        )
        assert post_warmup.returncode == 0, post_warmup.stdout + post_warmup.stderr
        scoped_report = json.loads((run / "post_warmup/report.json").read_text())
        assert scoped_report["tracking_error"]["status"] == "unavailable"
        assert scoped_report["tracking_error"]["sample_count"] == 0
        assert scoped_report["tracking_error"]["coverage_fraction"] == 0


def test_native_priority_refusal(tmp_path: Path, run_tool: RunTool) -> None:
    """Refuse a normal scheduler with FIFO priority through the actual capture CLI.

    Parameters
    ----------
    tmp_path
        Exclusive capture allocation.
    run_tool
        Actual public producer command.
    """
    config = tmp_path / "configuration.txt"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    output = tmp_path / "capture"
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(output),
        "--scheduler",
        "normal",
        "--priority",
        "1",
    )
    assert result.returncode == 1
    assert "native capture: FAIL" in result.stderr
    assert "priority" in (output / "native.log").read_text()
    assert not (output / "events.bin").exists()
