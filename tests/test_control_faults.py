# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fabric arithmetic capture and fault edge cases

"""Exercise real public ports of arithmetic, capture, monitor and injection modules."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


def test_fixed_point_references(run_rtl: RunRtl) -> None:
    """Exercise saturation, signed arithmetic and every sampled sine phase.

    Parameters
    ----------
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("plant_arithmetic_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    values = [
        int(line.split("value=")[1].split()[0])
        for line in result.stdout.splitlines()
        if line.startswith("REFERENCE")
    ]
    assert values[:5] == [1 << 24] * 5
    values = values[4:]
    assert values[1:17] == [round(math.sin(index * math.pi / 8) * (1 << 24)) for index in range(16)]
    assert values[17:21] == [index * (1 << 24) for index in range(4)]
    assert values[-7:-4] == [2147483647, -2147483648, 0]
    assert values[-1] == -3210182
    assert "ARITHMETIC_PASS" in result.stdout


def test_simultaneous_events_overflow_and_reset(run_rtl: RunRtl) -> None:
    """Keep original timestamps through wrapping queues and count all losses.

    Parameters
    ----------
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("control_event_capture_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GROUP_PASS wrapped=12 dropped=320" in result.stdout


@pytest.mark.parametrize("kind", [0, 1, 2, 3])
def test_fault_schedule_and_action_duration(kind: int, run_rtl: RunRtl) -> None:
    """Refuse invalid/replaced arms and apply exactly the selected action duration.

    Parameters
    ----------
    kind
        Fault selector.
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("fault_injector_tb", {"KIND": kind}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"INJECTOR_PASS kind={kind}" in result.stdout


def test_deadline_recovery_and_latch(run_rtl: RunRtl) -> None:
    """Check strict deadline edges, consecutive recovery and the persistent latch.

    Parameters
    ----------
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("deadline_monitor_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MONITOR_PASS" in result.stdout


@pytest.mark.parametrize(
    ("parameter", "value", "diagnostic"),
    [
        ("PERIOD_TICKS", 1, "PERIOD_TICKS must be at least two"),
        ("MISS_LIMIT", 0, "MISS_LIMIT must be positive"),
        ("GROUP_ADDRESS_BITS", 9, "GROUP_ADDRESS_BITS must be in [1,8]"),
    ],
)
def test_unsupported_parameters(
    parameter: str,
    value: int,
    diagnostic: str,
    run_rtl: RunRtl,
) -> None:
    """Refuse elaborated hardware configurations outside the supported contract.

    Parameters
    ----------
    parameter
        Unsupported public parameter.
    value
        Invalid parameter value.
    diagnostic
        Required refusal reason.
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("control_parameters_tb", {parameter: value}, [])
    assert result.returncode != 0
    assert diagnostic in result.stdout
