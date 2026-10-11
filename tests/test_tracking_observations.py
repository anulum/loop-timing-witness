# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capture-bound observed tracking tests

"""Exercise observed tracking through hash-bound manifests and the public analyzer."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from conftest import MakeRtlRun, RunTool


@pytest.mark.parametrize(
    "content",
    [
        "cycle,reference,output\n0,1,0.9\n1,2,1.8\n2,3,2.7\n",
        "cycle,reference,output\n",
        "cycle,reference,output\n0,1,0.9\n",
        "cycle,reference,output\n0,NaN,1\n",
        "cycle,reference,output\n0,1\n",
        "cycle,reference,output\n-1,1,0\n",
        "cycle,reference,output\n3,1,0\n",
        "cycle,reference,output\n0,abc,0\n",
        "cycle,reference,output\n0,1,0,extra\n",
        "cycle,reference,output\n0,1,0\n0,1,0\n",
        "wrong,reference,output\n0,1,0\n",
        "cycle,reference,output\n0,1e200,0\n1,1,0\n2,1,0\n",
        "cycle,reference,output\n0,1e500000,0\n1,1,0\n2,1,0\n",
    ],
)
def test_analyzer_observations(content: str, make_rtl_run: MakeRtlRun, run_tool: RunTool) -> None:
    """Reject missing, invented or malformed observations against actual fabric reads.

    Parameters
    ----------
    content
        Complete simulation series or intentionally corrupted input bytes.
    make_rtl_run
        Actual Icarus event capture and declared simulation data.
    run_tool
        Public host analyzer process.
    """
    run, manifest = make_rtl_run()
    tracking = run / "tracking.csv"
    tracking.write_text(content, encoding="utf-8")
    manifest["tracking_sampling"] = "observed"
    manifest["files"]["tracking"]["sha256"] = hashlib.sha256(tracking.read_bytes()).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = run_tool(
        "analyze_run", str(run / "manifest.json"), "--output-dir", str(run / "report")
    )
    if content == "cycle,reference,output\n0,1,0.9\n1,2,1.8\n2,3,2.7\n":
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads((run / "report/report.json").read_text())
        assert report["tracking_error"]["sample_count"] == 3
        assert report["tracking_error"]["missing_cycles"] == []
    else:
        assert result.returncode == 1
        assert not (run / "report").exists()


@pytest.mark.parametrize("coverage", ["partial", "empty"])
def test_missing_captured_samples_remain_explicit(
    coverage: str, make_rtl_run: MakeRtlRun, run_tool: RunTool
) -> None:
    """Report incomplete observed tracking without inventing missing samples.

    Parameters
    ----------
    coverage
        Whether two captured reads remain or all captured reads are absent.
    make_rtl_run
        Actual Icarus capture whose event and tracking subsets remain matched.
    run_tool
        Public analyser process consuming the digest-bound partial input.
    """
    run, manifest = make_rtl_run()
    observed_cycles = {0, 2} if coverage == "partial" else set()
    events = run / "events.bin"
    original = events.read_bytes()
    records = [original[offset : offset + 16] for offset in range(0, len(original), 16)]
    events.write_bytes(
        b"".join(
            record
            for record in records
            if record[0] != 2 or int.from_bytes(record[4:8], "little") in observed_cycles
        )
    )
    tracking = run / "tracking.csv"
    rows = tracking.read_text(encoding="utf-8").splitlines()
    selected_rows = [row for row in rows[1:] if int(row.split(",", 1)[0]) in observed_cycles]
    tracking.write_text("\n".join([rows[0], *selected_rows]) + "\n", encoding="utf-8")
    manifest["tracking_sampling"] = "observed"
    for name, path in {"events": events, "tracking": tracking}.items():
        manifest["files"][name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = run_tool(
        "analyze_run", str(run / "manifest.json"), "--output-dir", str(run / "report")
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((run / "report/report.json").read_text())
    metric = report["tracking_error"]
    assert report["valid"] is False
    assert report["evidence_status"] == "simulation_only"
    assert metric["sampling"] == "observed"
    assert metric["status"] == ("partial" if observed_cycles else "unavailable")
    assert metric["sample_count"] == len(observed_cycles)
    assert metric["expected_cycle_count"] == 3
    assert metric["missing_cycles"] == sorted({0, 1, 2} - observed_cycles)
    assert metric["coverage_fraction"] == pytest.approx(len(observed_cycles) / 3)
    if observed_cycles:
        assert metric["rms"] == pytest.approx(0.22360679774997896)
        assert metric["peak_absolute"] == pytest.approx(0.3)
    else:
        assert metric["reason"] == "no observed post-warmup samples"
        assert "rms" not in metric
        assert "peak_absolute" not in metric
