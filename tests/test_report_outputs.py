# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — report transaction tests

"""Exercise complete and failed report writes on real filesystem paths."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from report_outputs import write_report

MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]
RECORD_BYTES = 16


def test_missing_output_parent_is_refused(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A report cannot silently create an unreviewed parent directory.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        Parent of the absent directory.
    """
    run, _ = make_rtl_run()
    output = tmp_path / "missing" / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert "report parent does not exist" in result.stderr
    assert not output.exists()


def test_interrupted_staging_is_removed(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A post-staging failure leaves no partial report or shadow directory.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        Report staging parent.
    """
    run, _ = make_rtl_run()
    completed = tmp_path / "complete"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(completed))
    assert result.returncode == 0, result.stderr
    report = json.loads((completed / "report.json").read_text(encoding="utf-8"))
    report["energy"]["per_rail"] = None
    target = tmp_path / "interrupted"
    with pytest.raises(TypeError):
        write_report(target, report, [])
    assert not target.exists()
    assert not list(tmp_path.glob(".interrupted.*"))


def test_empty_interval_plot_is_still_labelled(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A COMPUTE stream with no interval pairs yields a provenance-labelled chart.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog COMPUTE producer.
    run_tool
        Host command runner.
    tmp_path
        Report parent.
    """
    run, manifest = make_rtl_run("COMPUTE")
    original = (run / "events.bin").read_bytes()
    records = [
        original[offset : offset + RECORD_BYTES] for offset in range(0, len(original), RECORD_BYTES)
    ]
    data = b"".join(record for record in records if record[0] == 8)
    (run / "events.bin").write_bytes(data)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(data).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "compute-report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    svg = (output / "interval_p99.svg").read_text(encoding="utf-8")
    assert "simulation_only" in svg
    assert "99th percentile event intervals" in svg
