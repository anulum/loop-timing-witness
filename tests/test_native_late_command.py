# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — independent late-command witness

"""Distinguish successful register submission from actual timely actuator acceptance."""

from __future__ import annotations

import csv
import struct
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import check_native_commands, configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


@pytest.mark.parametrize("mode", ["pid", "lqr"])
def test_submitted_command_can_be_late(
    native_run: Path, native_controllers: tuple[Path, Path], tmp_path: Path, mode: str
) -> None:
    """Preserve a real late command despite successful AXI submission and no safe latch.

    Parameters
    ----------
    native_run
        Actual mechanical or thermal RTL run executable.
    native_controllers
        Public C and Rust controller streaming executables for every returned command.
    tmp_path
        Exclusive input and actual witness output allocation.
    mode
        Actual PID or LQR controller selection.
    """
    config = tmp_path / "run.conf"
    config.write_text(
        configuration(mode, "overload")
        .replace("overload 0 3", "overload 0 1")
        .replace("1000 1100000", "1000 500000"),
        encoding="utf-8",
    )
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
    assert summary["samples"] == "32"
    assert summary["misses"] == "1"
    assert summary["safe"] == "0"
    assert summary["overflow"] == "0"
    records = list(struct.iter_unpack("<IIQ", events.read_bytes()))
    assert len(records) == int(summary["records"])
    assert [cycle for code, cycle, _ in records if code == 13] == [1]
    with raw.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 32
    assert rows[0]["cycle"] == "0"
    assert rows[0]["submitted"] == "1"
    assert rows[0]["overload_work"] == "332833500"
    check_native_commands(mode, rows, native_controllers)
