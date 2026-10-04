# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public package exports and independent JSON consumers

"""Exercise package initialization and public analysis on actual RTL captures."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from conftest import MakeRtlRun


def test_json_consumer_preserves_manifest_without_analysis(make_rtl_run: MakeRtlRun) -> None:
    """Round-trip an actual RTL manifest without initializing analysis.

    Parameters
    ----------
    make_rtl_run
        Real Icarus event capture and its source-bound simulation manifest.
    """
    run, manifest = make_rtl_run()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, sys
from pathlib import Path
import loop_timing_witness as package
from loop_timing_witness.manifest_io import (
    canonical_json_bytes, load_json_object, write_bytes_atomic,
)
source = Path(sys.argv[1])
value = load_json_object(source)
destination = source.with_name("json-consumer-manifest.json")
write_bytes_atomic(destination, canonical_json_bytes(value))
assert load_json_object(destination) == value
assert package.__all__ == ["RunInputs", "build_report", "load_run"]
assert set(package.__all__) <= set(dir(package))
sentinel = object()
assert getattr(package, "unregistered_analysis_attribute", sentinel) is sentinel
assert "loop_timing_witness.analyze_run" not in sys.modules
assert "loop_timing_witness.run_manifest" not in sys.modules
print(json.dumps(value, sort_keys=True))
""",
            str(run / "manifest.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == manifest


@pytest.mark.parametrize("first_export", ["RunInputs", "load_run", "build_report"])
def test_public_exports_analyse_actual_rtl_and_refuse_changed_events(
    make_rtl_run: MakeRtlRun, first_export: str
) -> None:
    """Preserve analysis, wildcard imports and digest refusal for every first export.

    Parameters
    ----------
    make_rtl_run
        Actual fabric records and validated simulation metadata.
    first_export
        Public class or function requested before the other exports.
    """
    run, _ = make_rtl_run()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, sys
from pathlib import Path
import loop_timing_witness as package
path = Path(sys.argv[1])
first_name = sys.argv[2]
assert set(package.__all__) <= set(dir(package))
first = getattr(package, first_name)
inputs = package.load_run(path)
assert isinstance(inputs, package.RunInputs)
copy = package.RunInputs(inputs.manifest, inputs.domain, inputs.files, inputs.directory)
report, rows = package.build_report(copy)
from loop_timing_witness.analyze_run import build_report as direct_report
assert (report, rows) == direct_report(inputs)
assert report["evidence_status"] == "simulation_only"
assert report["schema"] == "loop-timing-witness.analysis-report.v1"
assert rows == [
    {"cycle": 0, "interval": "scheduling_latency", "ticks": 10},
    {"cycle": 0, "interval": "compute_time", "ticks": 10},
    {"cycle": 0, "interval": "loop_latency", "ticks": 20},
    {"cycle": 1, "interval": "scheduling_latency", "ticks": 10},
    {"cycle": 1, "interval": "compute_time", "ticks": 10},
    {"cycle": 1, "interval": "loop_latency", "ticks": 20},
    {"cycle": 2, "interval": "scheduling_latency", "ticks": 10},
    {"cycle": 2, "interval": "compute_time", "ticks": 5000},
    {"cycle": 2, "interval": "loop_latency", "ticks": 5010},
]
namespace = {}
exec("from loop_timing_witness import *", namespace)
assert namespace["RunInputs"] is package.RunInputs
assert namespace["load_run"](path) == inputs
assert namespace["build_report"](inputs) == (report, rows)
assert getattr(package, first_name) is first
try:
    getattr(package, "unregistered_analysis_attribute")
except AttributeError as error:
    assert "unregistered_analysis_attribute" in str(error)
else:
    raise AssertionError("unsupported package attribute was accepted")
events = path.parent / inputs.manifest["files"]["events"]["path"]
events.write_bytes(events.read_bytes() + bytes([0]))
try:
    package.load_run(path)
except ValueError as error:
    assert "input SHA-256 mismatch: events.bin" in str(error)
else:
    raise AssertionError("changed captured event bytes were accepted")
print(json.dumps({"first_export": first_name, "evidence_status": report["evidence_status"]}))
""",
            str(run / "manifest.json"),
            first_export,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "first_export": first_export,
        "evidence_status": "simulation_only",
    }
