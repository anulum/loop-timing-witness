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
from typing import TYPE_CHECKING

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
    kp, ki, decay, gain, kx, kv, nr, lower, upper, ilower, iupper = configuration
    integral = derivative = previous = 0
    initialized = False
    output = []
    for row in rows:
        if row == "reset":
            integral = derivative = previous = 0
            initialized = False
            continue
        cycle, reference, position, velocity = map(int, row.split(","))
        held = False
        if mode == "lqr":
            raw = (nr * reference - kx * position - kv * velocity) // SCALE
        else:
            error = reference - position
            derivative = (
                max(
                    MINIMUM,
                    min(MAXIMUM, (decay * derivative - gain * (position - previous)) // SCALE),
                )
                if initialized
                else 0
            )
            proposed = max(ilower, min(iupper, (integral * SCALE + ki * error) // SCALE))
            provisional = (kp * error + (integral + derivative) * SCALE) // SCALE
            held = (provisional >= upper and error > 0) or (provisional <= lower and error < 0)
            if not held:
                integral = proposed
            raw = (kp * error + (integral + derivative) * SCALE) // SCALE
            previous = position
            initialized = True
        output.append(
            f"{cycle},{max(lower, min(upper, raw))},"
            f"{integral},{derivative},{int(raw < lower or raw > upper)},{int(held)}"
        )
    return "\n".join(output) + "\n"


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
    payload = ",".join(map(str, configuration)) + "\n" + "\n".join(rows) + "\n"
    expected = oracle(mode, configuration, rows)
    for binary in native_controllers:
        result = subprocess.run(
            [str(binary), mode], input=payload, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected
    vectors = tmp_path / "vectors.csv"
    output = tmp_path / "commands.csv"
    vectors.write_text(payload, encoding="utf-8")
    result = run_rtl(
        "controller_parity_tb",
        {},
        [
            f"+INPUT={vectors}",
            f"+OUTPUT={output}",
            f"+MODE={int(mode == 'lqr')}",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_text(encoding="utf-8") == expected


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
    for binary in native_controllers:
        result = subprocess.run(
            [str(binary), "pid"], input=payload, text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected
    vectors = tmp_path / "integrator.csv"
    output = tmp_path / "integrator-output.csv"
    vectors.write_text(payload, encoding="utf-8")
    result = run_rtl(
        "controller_parity_tb",
        {},
        [
            f"+INPUT={vectors}",
            f"+OUTPUT={output}",
            "+MODE=0",
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_text(encoding="utf-8") == expected
