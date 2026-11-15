# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — controller public CLI and RTL arithmetic parity

"""Compare full-range state trajectories through actual native and RTL entry points."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunRtl

SCALE = 1 << 24
MINIMUM = -(1 << 31)
MAXIMUM = (1 << 31) - 1
DEFAULT = (
    2 * SCALE,
    SCALE // 1000,
    SCALE // 2,
    SCALE // 4,
    2 * SCALE,
    SCALE,
    3 * SCALE,
    -4 * SCALE,
    4 * SCALE,
    -2 * SCALE,
    2 * SCALE,
)
# Integral, derivative, previous position, and whether a sample was taken.
RESET: Final[tuple[int, int, int, bool]] = (0, 0, 0, False)


def oracle(mode: str, configuration: tuple[int, ...], rows: list[str]) -> str:
    """Calculate the specified quantized recurrence using unbounded integers.

    Parameters
    ----------
    mode
        PID or discrete LQR.
    configuration
        Raw coefficient row.
    rows
        Cycle/reference/state rows and explicit reset boundaries.

    Returns
    -------
    str
        Exact expected six-field command stream.
    """
    kx, kv, nr, lower, upper = configuration[4:9]
    state = RESET
    output = []
    for row in rows:
        if row == "reset":
            state = RESET
            continue
        cycle, reference, position, velocity = map(int, row.split(","))
        held = False
        if mode == "lqr":
            raw = (nr * reference - kx * position - kv * velocity) // SCALE
        else:
            raw, held, state = _pid_step(configuration, state, reference, position)
        integral, derivative = state[:2]
        output.append(
            f"{cycle},{max(lower, min(upper, raw))},"
            f"{integral},{derivative},{int(raw < lower or raw > upper)},{int(held)}"
        )
    return "\n".join(output) + "\n"


def _pid_step(
    configuration: tuple[int, ...],
    state: tuple[int, int, int, bool],
    reference: int,
    position: int,
) -> tuple[int, bool, tuple[int, int, int, bool]]:
    """Advance the quantized PID recurrence by one sample.

    Parameters
    ----------
    configuration
        Raw coefficient row.
    state
        Integral, derivative, previous position and whether a sample was taken.
    reference, position
        This sample's reference and position.

    Returns
    -------
    tuple[int, bool, tuple[int, int, int, bool]]
        Unclipped command, whether anti-windup held the integral, and the new state.
    """
    kp, ki, decay, gain, _, _, _, lower, upper, ilower, iupper = configuration
    integral, derivative, previous, initialized = state
    error = reference - position
    derivative = (
        max(MINIMUM, min(MAXIMUM, (decay * derivative - gain * (position - previous)) // SCALE))
        if initialized
        else 0
    )
    proposed = max(ilower, min(iupper, (integral * SCALE + ki * error) // SCALE))
    provisional = (kp * error + (integral + derivative) * SCALE) // SCALE
    held = (provisional >= upper and error > 0) or (provisional <= lower and error < 0)
    if not held:
        integral = proposed
    raw = (kp * error + (integral + derivative) * SCALE) // SCALE
    return raw, held, (integral, derivative, position, True)


def _check_native(binaries: tuple[Path, Path], mode: str, payload: str, expected: str) -> None:
    """Require each native public program to print the expected command stream.

    Parameters
    ----------
    binaries
        Actual native CLI programs.
    mode
        Controller selection.
    payload
        Coefficient row and sample rows.
    expected
        Exact expected command stream.
    """
    for binary in binaries:
        result = subprocess.run(
            [str(binary), mode], input=payload, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected


def _rtl_commands(run_rtl: RunRtl, vectors: Path, output: Path, mode: str, payload: str) -> str:
    """Run the controller parity testbench on one payload and return its commands.

    Parameters
    ----------
    run_rtl
        Public fabric simulator.
    vectors, output
        Managed input and output files.
    mode
        Controller selection.
    payload
        Coefficient row and sample rows.

    Returns
    -------
    str
        The testbench's command stream.
    """
    vectors.write_text(payload, encoding="utf-8")
    result = run_rtl(
        "controller_parity_tb",
        {},
        [f"+INPUT={vectors}", f"+OUTPUT={output}", f"+MODE={int(mode == 'lqr')}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output.read_text(encoding="utf-8")


def _full_range_rows() -> list[str]:
    """Return extreme and pseudo-random sample rows followed by a reset and a restart.

    Returns
    -------
    list[str]
        Cycle/reference/position/velocity rows and the ``reset`` boundary.
    """
    rows = [
        f"{cycle},{reference},{position},{velocity}"
        for cycle, reference, position, velocity in [
            (0, MAXIMUM, MINIMUM, MAXIMUM),
            (1, MINIMUM, MAXIMUM, MINIMUM),
            (2, 0, -1, -1),
            (3, 0, 1, 1),
            (4, SCALE, 0, 0),
            (5, -SCALE, 0, 0),
            (6, 0, 0, 0),
            (MAXIMUM * 2 + 1, 1, 2, 3),
        ]
    ]
    state = 1729
    for cycle in range(8, 520):
        values = []
        for _ in range(3):
            state = (1664525 * state + 1013904223) % (1 << 32)
            values.append(state - (1 << 31))
        rows.append(f"{cycle}," + ",".join(map(str, values)))
    rows.extend(["reset", "0,16777216,0,0", "1,33554432,0,0", "2,0,0,0"])
    return rows


@pytest.mark.parametrize("mode", ["pid", "lqr"])
@pytest.mark.parametrize(
    "configuration",
    [
        DEFAULT,
        (
            MAXIMUM,
            MAXIMUM,
            SCALE,
            MAXIMUM,
            MINIMUM,
            MAXIMUM,
            MINIMUM,
            MINIMUM,
            MAXIMUM,
            MINIMUM,
            MAXIMUM,
        ),
    ],
)
def test_native_and_rtl_full_range_parity(
    mode: str,
    configuration: tuple[int, ...],
    native_controllers: tuple[Path, Path],
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Check extremes, fractional negatives, anti-windup, clipping and reset.

    Parameters
    ----------
    mode
        Controller selection.
    configuration
        Default or maximal-width coefficients.
    native_controllers
        Actual native CLI programs.
    run_rtl
        Public fabric simulator.
    tmp_path
        Managed simulation vectors and output.
    """
    rows = _full_range_rows()
    payload = ",".join(map(str, configuration)) + "\n" + "\n".join(rows) + "\n"
    expected = oracle(mode, configuration, rows)
    _check_native(native_controllers, mode, payload, expected)
    vectors, output = tmp_path / "vectors.csv", tmp_path / "commands.csv"
    assert _rtl_commands(run_rtl, vectors, output, mode, payload) == expected


@pytest.mark.parametrize(
    "sample",
    [
        "-0,0,0,0",
        "4294967296,0,0,0",
        "0,2147483648,0,0",
        "0,0,0",
        "0,0,0,0,0",
        " 0,0,0,0",
        "0,0,0,0junk",
        "-1,0,0,0",
        "0,0,bad,0",
        "0,0,0,bad",
    ],
)
def test_native_stream_refuses_malformed_samples(
    sample: str,
    native_controllers: tuple[Path, Path],
) -> None:
    """Reject sample parsing ambiguities in both public programs.

    Parameters
    ----------
    sample
        Malformed cycle or state row.
    native_controllers
        Native public programs.
    """
    payload = ",".join(map(str, DEFAULT)) + "\n" + sample + "\n"
    for binary in native_controllers:
        result = subprocess.run(
            [str(binary), "pid"], input=payload, text=True, capture_output=True, check=False
        )
        assert result.returncode == 1
        assert "invalid sample row" in result.stderr
        assert result.stdout == ""


def test_integral_rail_recovery_and_reset(
    native_controllers: tuple[Path, Path],
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """A pure integrator must reach the rail, hold, then recover in all languages.

    Parameters
    ----------
    native_controllers
        Actual native public entry points.
    run_rtl
        Public controller RTL simulation.
    tmp_path
        Managed vector directory.
    """
    configuration = (0, SCALE, 0, 0, SCALE, SCALE, SCALE, -SCALE, SCALE, -10 * SCALE, 10 * SCALE)
    rows = [
        "0,33554432,0,0",
        "1,33554432,0,0",
        "2,-33554432,0,0",
        "reset",
        "0,-33554432,0,0",
        "1,-33554432,0,0",
        "2,33554432,0,0",
    ]
    payload = ",".join(map(str, configuration)) + "\n" + "\n".join(rows) + "\n"
    expected = (
        "0,16777216,33554432,0,1,0\n1,16777216,33554432,0,1,1\n"
        "2,0,0,0,0,0\n0,-16777216,-33554432,0,1,0\n"
        "1,-16777216,-33554432,0,1,1\n2,0,0,0,0,0\n"
    )
    _check_native(native_controllers, "pid", payload, expected)
    vectors, output = tmp_path / "integrator.csv", tmp_path / "integrator-output.csv"
    assert _rtl_commands(run_rtl, vectors, output, "pid", payload) == expected
