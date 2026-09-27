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
