# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — production AXI witness binary event integration

"""Run actual register, plant and FIFO transactions through the production top."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import struct
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT, MakeRtlRun, RunTool

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize(
    "scenario", [(bus, thermal) for bus in [3, 5, 7, 11, 19] for thermal in [0, 1]]
)
def test_production_axi_records(
    scenario: tuple[int, int], run_rtl: RunRtl, make_rtl_run: MakeRtlRun, run_tool: RunTool
) -> None:
    """Retain original edge timestamps through AXI word reads and explicit POP.

    Parameters
    ----------
    scenario
        Bus half period and actual mechanical or thermal plant selection.
    run_rtl
        Repository compiler and bounded simulator entry point.
    make_rtl_run
        Real simulation manifest factory; new top outputs replace its capture files.
    run_tool
        Public host analyzer subprocess runner.
    """
    bus_half_period, thermal = scenario
    run, manifest = make_rtl_run()
    events = run / "events.bin"
    tracking = run / "tracking_raw.csv"
    result = run_rtl(
        "axi_control_witness_tb",
        {"BUS_HALF_PERIOD": bus_half_period, "THERMAL": thermal},
        [f"+EVENT_FILE={events}", f"+TRACK_FILE={tracking}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AXI_TOP_PASS records=8 drained=1 reset_reuse=1" in result.stdout
    assert "RETAINED_IRQ_PASS old_ack=preserved coalesced=1 reset=cleared" in result.stdout
    records = list(struct.iter_unpack("<IIQ", events.read_bytes()))
    assert [record[0] for record in records] == [1, 2, 3, 4, 1, 2, 3, 4]
    assert [record[1] for record in records] == [0, 0, 0, 0, 1, 1, 1, 1]
    assert records[4][2] - records[0][2] == 32768
    assert records[7][2] - records[3][2] == 32768
    assert all(records[index][2] <= records[index + 1][2] for index in range(7))
    assert len(tracking.read_text().splitlines()) == 3
    analyze_simulation(run, manifest, scenario, run_tool)


def analyze_simulation(
    run: Path, manifest: dict[str, Any], scenario: tuple[int, int], run_tool: RunTool
) -> None:
    """Bind the real AXI drain to source hashes and the public host report.

    Parameters
    ----------
    run
        Exact run directory produced by the RTL test.
    manifest
        Simulation manifest to bind to the production top and its actual outputs.
    scenario
        Bus half period and plant selection.
    run_tool
        Public host analyzer subprocess runner.
    """
    bus_half_period, thermal = scenario
    sources = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in sorted((REPOSITORY_ROOT / "rtl").glob("*.sv"))
    ]
    sources.append("tests/rtl/axi_control_witness_tb.sv")
    for relative in sources:
        destination = run / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, destination)
    shutil.copyfile(run.parent / "axi_control_witness_tb.vvp", run / "axi_control_witness_tb.vvp")
    with (run / "tracking_raw.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    (run / "tracking.csv").write_text(
        "cycle,reference,output\n"
        + "".join(
            f"{row['cycle']},{int(row['reference_raw']) / (1 << 24)},"
            f"{int(row['output_raw']) / (1 << 24)}\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    manifest["run_id"] = f"axi-top-{thermal}-{bus_half_period}"
    manifest["cycle_count"] = 2
    manifest["sample_period_ticks"] = 32768
    manifest["files"]["power"] = None
    manifest["fault_schedule"] = []
    manifest["plant"]["name"] = "first_order_thermal" if thermal else "second_order_mechanical"
    manifest["plant"]["fixed_point_format"] = "Q8.24"
    manifest["controller"] = {
        "name": "simulation_constant_command",
        "coefficients": {"command_raw": 16777216},
    }
    manifest["operator_notes"] = (
        "Simulation: testbench drives constant commands through production AXI; "
        "no processor timing or power measurements."
    )
    manifest["source"]["files"] = [
        {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}
        for relative in [*sources, "axi_control_witness_tb.vvp", "tracking_raw.csv"]
    ]
    for name in ("events", "tracking"):
        manifest["files"][name]["sha256"] = hashlib.sha256(
            (run / manifest["files"][name]["path"]).read_bytes()
        ).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = run / "reports"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text())
    assert report["evidence_status"] == "simulation_only"
    assert report["fifo_overflow_count"] == 0
    assert report["events"]["control"]["deadline_misses"] == 0
