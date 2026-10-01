# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original RTL counter progression and common reset

"""Compile the saturation driver and exercise original counters through public ports."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def test_original_counter_progression_and_reset(tmp_path: Path) -> None:
    """Run a bounded prefix of the unchanged full 32-bit saturation programme.

    Parameters
    ----------
    tmp_path
        Exclusive build and raw coverage allocation.

    Notes
    -----
    The ordinary suite checks compilation, progression and reset in one million
    ticks. ``make rtl-counter-saturation`` executes the complete 32-bit run;
    this shorter test does not claim that the saturation branches were reached.
    """
    result = subprocess.run(
        [
            "make",
            "rtl-counter-saturation",
            f"RTL_SATURATION_DIRECTORY={tmp_path}",
            "RTL_SATURATION_STEPS=1000000",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CHECK steps=1000000 late=1000000 misses=1000000 overflow=1000021" in result.stdout
    assert "PUBLIC32_PASS steps=1000000 saturated=0" in result.stdout
    assert (tmp_path / "coverage.dat").stat().st_size > 0
    assert (tmp_path / "coverage.dat.at-1000000").stat().st_size > 0
