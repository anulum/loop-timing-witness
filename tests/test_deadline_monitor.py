# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — deadline monitor threshold and strict compiler contract

"""Check parameterised strict deadlines, recovery, safe latch and common reset."""

from __future__ import annotations

import subprocess

import pytest

from conftest import REPOSITORY_ROOT, RunRtl


@pytest.mark.parametrize("limit", [1, 2, 3, 7])
def test_strict_deadline_limit(limit: int, run_rtl: RunRtl) -> None:
    """Compile without suppressed warnings and observe exact trip edges through public ports.

    Parameters
    ----------
    limit
        Positive consecutive-miss threshold, including immediate first-miss trip.
    run_rtl
        Actual production RTL compiler and simulator entry point.
    """
    lint = subprocess.run(
        [
            "verilator",
            "--lint-only",
            "--Wall",
            "--top-module",
            "deadline_monitor",
            f"-GMISS_LIMIT=32'd{limit}",
            str(REPOSITORY_ROOT / "rtl/deadline_monitor.sv"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr
    assert lint.stderr == ""
    result = run_rtl("deadline_monitor_tb", {"MISS_LIMIT": limit}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MONITOR_PASS" in result.stdout
