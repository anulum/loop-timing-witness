# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AXI run configuration waveform and fault tests

"""Configure actual reference and fault modules through production bus registers."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize("bus_half_period", [3, 19])
@pytest.mark.parametrize("thermal", [0, 1])
@pytest.mark.parametrize("fault", [0, 1, 2, 3])
@pytest.mark.parametrize("reference", [0, 1, 2])
def test_configured_run(
    bus_half_period: int, thermal: int, fault: int, reference: int, run_rtl: RunRtl
) -> None:
    """Retain configuration provenance through real waveforms and fault actions.

    Parameters
    ----------
    bus_half_period
        Bus half period around the 5 ns capture clock.
    thermal
        Select the actual mechanical or thermal plant.
    fault
        Select drop, delay, freeze or software overload request.
    reference
        Select the actual step, ramp or sine waveform.
    run_rtl
        Repository compiler and bounded simulator entry point.
    """
    result = run_rtl(
        "control_io_registers_tb",
        {
            "BUS_HALF_PERIOD": bus_half_period,
            "THERMAL": thermal,
            "CONFIGURATION_ONLY": 1,
            "FAULT_KIND": fault,
            "REFERENCE_MODE": reference,
        },
        [],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUN_CONFIGURATION_PASS immutable=1 waveform=actual faults=actual" in result.stdout
