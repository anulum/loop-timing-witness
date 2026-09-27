# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public native configuration validation

"""Require semantic API validation before any actual RTL configuration change."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_lifecycle_api import lifecycle_program
from test_native_run import configuration

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["lifecycle_program"]


@pytest.mark.parametrize(
    "scenario",
    [
        "cycles_zero",
        "period_zero",
        "coefficients",
        "reference",
        "phase",
        "kind",
        "duration",
        "disabled_kind",
        "disabled_cycle",
        "disabled_periods",
        "unused_work",
        "unused_delay",
        "fault_cycle",
        "fault_periods",
        "work_bound",
        "delay_bound",
    ],
)
def test_configuration_api_refusal(lifecycle_program: Path, tmp_path: Path, scenario: str) -> None:
    """Reject malformed public structures and complete a real healthy run afterward.

    Parameters
    ----------
    lifecycle_program
        Actual native API executable linked to a production RTL plant.
    tmp_path
        Exclusive configuration and captured output allocation.
    scenario
        Semantic field or relationship violated by the public API caller.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none").replace("pid 32", "pid 2"))
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [str(lifecycle_program), "config_" + scenario, str(config), str(events), str(raw)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified config_{scenario}\n"
    assert result.stderr == ""
    assert events.stat().st_size > 0
    assert len(raw.read_text().splitlines()) == 3
    assert (tmp_path / "events.bin.previous").stat().st_size > 0
    assert len((tmp_path / "raw.csv.previous").read_text().splitlines()) == 3
