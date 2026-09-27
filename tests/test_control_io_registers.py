# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capture registers through actual AXI plant transactions

"""Exercise snapshot, staging and safety semantics through production RTL ports."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize("bus_half_period", [3, 5, 7, 11, 19])
@pytest.mark.parametrize("thermal", [0, 1])
def test_capture_register_transactions(bus_half_period: int, thermal: int, run_rtl: RunRtl) -> None:
    """Observe real sample events and actuator updates across asynchronous AXI clocks.

    Parameters
    ----------
    bus_half_period
        Bus half period in nanoseconds around the 5 ns capture half period.
    thermal
        Select the actual mechanical or thermal plant.
    run_rtl
        Repository compiler and bounded simulator entry point.
    """
    result = run_rtl(
        "control_io_registers_tb", {"BUS_HALF_PERIOD": bus_half_period, "THERMAL": thermal}, []
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROL_REGISTERS_PASS snapshot=coherent commands=atomic safe=latched" in result.stdout
