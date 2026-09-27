# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AXI transport integration against production plants

"""Exercise independent AXI channels and response credit across capture clocks."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize("bus_half_period", [3, 5, 7, 11, 19])
@pytest.mark.parametrize("thermal", [0, 1])
@pytest.mark.parametrize("local_aperture", [0, 1])
def test_axi_plant_transactions(
    bus_half_period: int, thermal: int, local_aperture: int, run_rtl: RunRtl
) -> None:
    """Transfer commands without coupling AXI address, data or response channels.

    Parameters
    ----------
    bus_half_period
        Bus half period in nanoseconds, around a capture half period of 5 ns.
    thermal
        Select the actual mechanical or thermal plant.
    local_aperture
        Keep upper addresses local for FIFO words or forward them to capture.
    run_rtl
        Repository compiler and bounded simulator entry point.
    """
    result = run_rtl(
        "axi_lite_clock_bridge_tb",
        {"BUS_HALF_PERIOD": bus_half_period, "THERMAL": thermal, "ENABLE_LOCAL": local_aperture},
        [],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AXI_BRIDGE_PASS" in result.stdout
    expected = (
        "FIFO_WINDOW_PASS immutable_words=4 records=3" if local_aperture else "REMOTE_APERTURE_PASS"
    )
    assert expected in result.stdout
