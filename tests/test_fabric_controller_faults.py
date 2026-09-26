# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fabric controller independence and safe-state fault paths

"""Verify real integrated fabric service and independent fault handling."""

from __future__ import annotations

import csv
import struct
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunRtl


@pytest.mark.parametrize(
    "scenario",
    [(thermal, lqr, invalid) for thermal in [0, 1] for lqr in [0, 1] for invalid in [0, 1]],
)
def test_fabric_refusal_and_freeze_keep_safe_priority(
    scenario: tuple[int, int, int],
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Refused config or actuator freeze trips the independent actuator monitor.

    Parameters
    ----------
    scenario
        Plant, controller and invalid-configuration selection.
    run_rtl
        Public integrated fabric simulator.
    tmp_path
        Managed drained-event and tracking files.
    """
    thermal, lqr, invalid = scenario
    result = run_rtl(
        "fabric_control_witness_tb",
        {
            "THERMAL": thermal,
            "LQR": lqr,
            "INVALID": invalid,
            "FAULT": -1 if invalid else 2,
        },
        [f"+EVENT_FILE={tmp_path / 'events.bin'}", f"+TRACK_FILE={tmp_path / 'plant.csv'}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"misses={5 if invalid else 4}" in result.stdout
    assert "late=0" in result.stdout
    with (tmp_path / "plant.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert all(int(row["actuator"]) == 0 for row in rows[3:])
    if invalid:
        assert all(int(row["actuator"]) == 0 for row in rows)


@pytest.mark.parametrize(
    "scenario",
    [(thermal, lqr, fault) for thermal in [0, 1] for lqr in [0, 1] for fault in [0, 1, 3]],
)
def test_fabric_service_ignores_processor_irq_faults(
    scenario: tuple[int, int, int], run_rtl: RunRtl, tmp_path: Path
) -> None:
    """Drop/delay IRQ and overload requests leave the fabric feedback loop timely.

    Parameters
    ----------
    scenario
        Plant, controller and processor-path fault selection.
    run_rtl
        Actual integrated fabric simulator.
    tmp_path
        Managed drain and sample files.
    """
    thermal, lqr, fault = scenario
    event_file = tmp_path / "irq-events.bin"
    result = run_rtl(
        "fabric_control_witness_tb",
        {"THERMAL": thermal, "LQR": lqr, "FAULT": fault},
        [f"+EVENT_FILE={event_file}", f"+TRACK_FILE={tmp_path / 'irq-plant.csv'}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "misses=0 late=0" in result.stdout
    events = list(struct.iter_unpack("<BBHIQ", event_file.read_bytes()))
    assert sum(event[0] == 6 for event in events) == 1
    assert not any(event[0] in (5, 7) for event in events)
    assert sum(event[0] == 3 for event in events) == 5
