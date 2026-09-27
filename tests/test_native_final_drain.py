# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual final backlog drain

"""Drain real retained events after a modeled workload spans the whole run."""

from __future__ import annotations

import csv
import json
import struct
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import check_native_commands, configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

__all__ = ["native_run"]


def backlog_configuration(mode: str) -> str:
    """Supply an eight-cycle actual fault with a five-millisecond modeled CPU delay.

    Parameters
    ----------
    mode
        Actual native PID or LQR kernel selection.

    Returns
    -------
    str
        Complete native configuration; event FIFO capacity is not substituted.
    """
    return (
        configuration(mode, "overload")
        .replace(f"{mode} 32", f"{mode} 8")
        .replace("overload 0 3", "overload 0 8")
        .replace("1000 1100000", "1000 5000000")
    )


@pytest.mark.parametrize("mode", ["pid", "lqr"])
def test_actual_final_backlog(
    native_run: Path, native_controllers: tuple[Path, Path], tmp_path: Path, mode: str
) -> None:
    """Retain all actual events after final drain and replay the observed command.

    Parameters
    ----------
    native_run
        Production native controller linked to the actual selected RTL plant.
    native_controllers
        Public C and Rust streaming kernel executables.
    tmp_path
        Exclusive configuration and actual binary/raw outputs.
    mode
        Actual controller kernel selection.
    """
    config = tmp_path / "run.conf"
    config.write_text(backlog_configuration(mode), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("simulation_only ")
    summary = dict(item.split("=") for item in result.stdout.split()[1:])
    assert summary == {"samples": "1", "records": "20", "misses": "8", "overflow": "0", "safe": "1"}
    records = list(struct.iter_unpack("<IIQ", events.read_bytes()))
    assert len(records) == 20
    assert [cycle for code, cycle, _ in records if code == 1] == list(range(8))
    assert [cycle for code, cycle, _ in records if code == 4] == list(range(8))
    assert [cycle for code, cycle, _ in records if code == 5] == [2]
    with raw.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["cycle"] == "0"
    assert rows[0]["submitted"] == "0"
    assert rows[0]["overload_work"] == "332833500"
    check_native_commands(mode, rows, native_controllers)


@pytest.mark.parametrize("thermal", [0, 1])
def test_capture_final_backlog(tmp_path: Path, run_tool: RunTool, thermal: int) -> None:
    """Bind the complete real backlog capture to its importer and report chain.

    Parameters
    ----------
    tmp_path
        Exclusive frozen source and actual capture allocation.
    run_tool
        Public repository tool entry-point runner.
    thermal
        Compile-time production plant selection.
    """
    config = tmp_path / "run.conf"
    config.write_text(backlog_configuration("lqr" if thermal else "pid"), encoding="utf-8")
    capture = tmp_path / "capture"
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(capture),
        "--thermal",
        str(thermal),
        "--fifo-address-bits",
        "5",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    metadata = json.loads((capture / "native_metadata.json").read_text())
    report = json.loads((capture / "reports/report.json").read_text())
    assert metadata["result"] == {
        "samples": 1,
        "records": 20,
        "misses": 8,
        "overflow": 0,
        "safe": True,
    }
    assert report["evidence_status"] == "simulation_only"
    assert report["events"]["control"]["observed_deadlines"] == 8
    assert report["tracking_error"]["sample_count"] == 1
    assert report["tracking_error"]["status"] == "partial"
    assert report["energy"]["status"] == "unavailable"
    assert report["valid"] is False
