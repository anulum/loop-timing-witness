# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — retained interrupt status and snapshot acknowledgement

"""Exercise the actual retained IRQ status across independent clock domains."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize("bus_half_period", [3, 7, 19])
def test_status_snapshot_and_new_generation(bus_half_period: int, run_rtl: RunRtl) -> None:
    """Retain a newer IRQ when acknowledging an older snapshot.

    Parameters
    ----------
    bus_half_period
        Bus half period relative to the five-nanosecond capture half period.
    run_rtl
        Repository compiler and bounded public-port simulation entry point.
    """
    result = run_rtl("retained_interrupt_tb", {"BUS_HALF_PERIOD": bus_half_period}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RETAINED_STATUS_PASS generations=4" in result.stdout
