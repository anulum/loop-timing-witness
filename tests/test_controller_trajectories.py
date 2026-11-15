# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — long quantized closed-loop behavior and native command parity

"""Assess real controller/plant feedback over sixty-four model seconds."""

from __future__ import annotations

import csv
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_controller_parity import DEFAULT, SCALE

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunRtl


def _closed_loop_rows(run_rtl: RunRtl, path: Path, thermal: int, lqr: int) -> list[dict[str, str]]:
    """Settle the fabric's closed loop for 64,000 samples and read its trajectory.

    Parameters
    ----------
    run_rtl
        Public fabric simulator.
    path
        Trajectory file.
    thermal, lqr
        Plant model and controller mode.

    Returns
    -------
    list[dict[str, str]]
        Trajectory rows.
    """
    simulation = run_rtl(
        "controller_closed_loop_tb", {"THERMAL": thermal, "LQR": lqr}, [f"+TRACK_FILE={path}"]
    )
    assert simulation.returncode == 0, simulation.stdout + simulation.stderr
    assert "CLOSED_LOOP_PASS samples=64000" in simulation.stdout
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 64000
    return rows


def _streams(configuration: tuple[int, ...], rows: list[dict[str, str]]) -> tuple[str, str]:
    """Return the native input stream of a trajectory and the commands the fabric issued.

    Parameters
    ----------
    configuration
        Raw coefficient row.
    rows
        Trajectory rows.

    Returns
    -------
    tuple[str, str]
        Coefficients and sample rows, and the fabric's six-field command stream.
    """
    payload = (
        ",".join(map(str, configuration))
        + "\n"
        + "".join(
            f"{row['cycle']},{row['reference']},{row['output']},{row['velocity']}\n" for row in rows
        )
    )
    expected = "".join(
        f"{row['cycle']},{row['command']},{row['integral']},{row['derivative']},"
        f"{row['clipped']},{row['held']}\n"
        for row in rows
    )
    return payload, expected


@pytest.mark.parametrize("scenario", [(thermal, lqr) for thermal in [0, 1] for lqr in [0, 1]])
def test_long_quantized_feedback(
    scenario: tuple[int, int],
    native_controllers: tuple[Path, Path],
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Settle the actual quantized plant and compare every native control transition.

    Parameters
    ----------
    scenario
        Mechanical/thermal plant and PID/LQR mode.
    native_controllers
        Actual public streaming kernel programs.
    run_rtl
        Public fabric simulator.
    tmp_path
        Managed trajectory files.
    """
    thermal, lqr = scenario
    rows = _closed_loop_rows(run_rtl, tmp_path / "closed-loop.csv", thermal, lqr)
    gains = (6944437, 0, 23721653) if thermal else (38822697, 26419076, 55599913)
    configuration = (DEFAULT[0], 16777, *DEFAULT[2:4], *gains, *DEFAULT[7:])
    payload, expected = _streams(configuration, rows)
    for binary in native_controllers:
        native = subprocess.run(
            [str(binary), "lqr" if lqr else "pid"],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )
        assert native.returncode == 0, native.stderr
        assert native.stdout == expected
    assert max(abs(int(row["output"])) for row in rows) < 2 * SCALE
    assert max(abs(int(row["reference"]) - int(row["output"])) for row in rows[-1000:]) < 4000
