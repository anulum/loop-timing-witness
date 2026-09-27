# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — production AXI response progress across bank states

"""Exercise the entire production aperture without substituting clock or decoder behavior."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_axi_simulator import simulator

__all__ = ["simulator"]

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("state", ["idle", "held", "finished"])
def test_aperture_response_progress(simulator: Path, tmp_path: Path, state: str) -> None:
    """Complete every aperture read and refuse all partial writes without mutating configuration.

    Parameters
    ----------
    simulator
        Production AXI process with the actual mechanical or thermal RTL model.
    tmp_path
        Retained requests, responses and measured simulation-time receipt.
    state
        Idle banks, asserted bank reset or an actual completed two-cycle run.
    """
    setup = {
        "idle": [],
        "held": ["W 152 0 15"],
        "finished": ["W 60 1 15", "W 56 1 15", "T 1000000"],
    }[state]
    # These registers hold configuration/staging; reads cannot acknowledge IRQs or pop FIFO data.
    registers = [40, 44, 56, 60, 68, 72, 76, 80, 84, 88, 92, 96, 100, 152]
    snapshot = [f"R {address}" for address in registers]
    reads = [f"R {address}" for address in range(256)]
    writes = [f"W {address} 1 {strobes}" for address in range(256) for strobes in range(15)]
    requests = [*setup, *snapshot, "T 0", *reads, *writes, *snapshot, "R 4", "Q"]
    payload = "\n".join(requests) + "\n"
    (tmp_path / "requests.txt").write_text(payload, encoding="utf-8")
    result = subprocess.run(
        [str(simulator)], input=payload, capture_output=True, text=True, check=False, timeout=10
    )
    (tmp_path / "responses.txt").write_text(result.stdout, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = [tuple(map(int, line.split(","))) for line in result.stdout.splitlines()]
    assert len(rows) == len(requests) - 1
    assert all(len(row) == 3 for row in rows)
    start = len(setup) + len(snapshot) + 1
    accesses = rows[start : start + len(reads) + len(writes)]
    previous = rows[start - 1][2]
    durations = []
    for index, (response, _data, elapsed) in enumerate(accesses):
        duration = elapsed - previous
        durations.append(duration)
        # This bound is for the fixed 7 ns/5 ns clocks and one serial transaction only.
        assert 0 < duration <= 280, (state, requests[start + index], duration)
        if index < len(reads):
            assert response in {0, 2}
            if index % 4:
                assert response == 2
        else:
            assert response == 2, requests[start + index]
        previous = elapsed
    before = [row[:2] for row in rows[len(setup) : len(setup) + len(snapshot)]]
    after = [row[:2] for row in rows[-len(snapshot) - 1 : -1]]
    assert after == before
    if state == "held":
        assert after[-1] == (0, 8)
    else:
        assert all(response == 0 for response, _data in after)
        assert after[-1][1] & 7 == 7
        assert bool(rows[-1][1] & 4) == (state == "finished")
    receipt = {
        "state": state,
        "reads": len(reads),
        "partial_writes": len(writes),
        "maximum_transaction_ns": max(durations),
        "duration_scope": "simulation_only",
        "configuration_unchanged": True,
    }
    (tmp_path / "progress.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
