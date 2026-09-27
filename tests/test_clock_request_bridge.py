# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — coherent request bridge plant integration tests

"""Exercise actual plant reads, actuator commands and drained capture timestamps."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize("bus_half_period", [3, 5, 7, 11, 19])
@pytest.mark.parametrize("thermal", [0, 1])
def test_coherent_plant_transactions(bus_half_period: int, thermal: int, run_rtl: RunRtl) -> None:
    """Keep snapshots coherent while accepting commands and applying backpressure.

    Parameters
    ----------
    bus_half_period
        Bus clock half period in simulator nanoseconds, around a 5 ns capture half period.
    thermal
        Select the actual mechanical or thermal plant implementation.
    run_rtl
        Repository compiler and bounded simulator entry point.
    """
    result = run_rtl(
        "clock_request_bridge_tb",
        {"BUS_HALF_PERIOD": bus_half_period, "THERMAL": thermal},
        [],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BRIDGE_PASS reads=5 writes=5 deadlines=5" in result.stdout


@pytest.mark.parametrize("parameter", ["REQUEST_BITS", "RESPONSE_BITS"])
@pytest.mark.parametrize("width", [0, -1])
def test_invalid_payload_width(parameter: str, width: int, run_rtl: RunRtl) -> None:
    """Refuse an invalid production bridge configuration before transactions.

    Parameters
    ----------
    parameter
        Request or response payload width parameter.
    width
        Nonpositive width that must terminate elaborated simulation.
    run_rtl
        Repository compiler and bounded simulator entry point.
    """
    result = run_rtl("clock_request_bridge_tb", {parameter: width}, [])
    assert result.returncode != 0
    assert "bridge payload widths must be positive" in result.stdout
