# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native controller feedback through simulated production AXI

"""Exercise a process transport around actual RTL, with C and Rust controllers."""

from __future__ import annotations

import select
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_controller_parity import DEFAULT, oracle

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module", params=[0, 1])
def simulator(request: pytest.FixtureRequest) -> Path:
    """Build the production mechanical or thermal RTL model with fatal warnings.

    Parameters
    ----------
    request
        Selected actual plant parameter.

    Returns
    -------
    Path
        Native AXI process executable.
    """
    thermal = int(request.param)
    result = subprocess.run(
        ["make", "axi-simulator", f"SIMULATION_THERMAL={thermal}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return REPOSITORY_ROOT / f"build/axi_simulator_{thermal}/axi_simulator"


def exchange(process: subprocess.Popen[str], message: str) -> tuple[int, int, int]:
    """Send one public protocol request and bound its response wait.

    Parameters
    ----------
    process
        Real simulator process with pipes.
    message
        Complete request without its newline.

    Returns
    -------
    tuple of int
        Actual AXI response, value and simulation nanoseconds.
    """
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(message + "\n")
    process.stdin.flush()
    assert select.select([process.stdout], [], [], 5)[0], message
    row = process.stdout.readline().strip().split(",")
    assert len(row) == 3, row
    return int(row[0]), int(row[1]), int(row[2])


def test_register_reset_and_irq(simulator: Path) -> None:
    """Use real local/remote registers, SLVERR, idle wait and held-bank lifecycle.

    Parameters
    ----------
    simulator
        Compiled production top process.
    """
    with subprocess.Popen(
        [str(simulator)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as process:
        try:
            assert exchange(process, "R 124")[1] == 1
            assert exchange(process, "R 125")[0] == 2
            assert exchange(process, "R 0")[0] == 2
            assert exchange(process, "W 152 0 15")[0] == 0
            assert exchange(process, "R 152")[1] == 8
            assert exchange(process, "R 124")[0] == 2
            assert exchange(process, "W 152 1 15")[0] == 0
            assert exchange(process, "T 140")[0] == 0
            assert exchange(process, "R 152")[1] & 7 == 7
            assert exchange(process, "I 0")[1] == 0
            before = exchange(process, "T 0")[2]
            assert exchange(process, "T 123")[2] - before == 123
            assert exchange(process, "W 56 1 1")[0] == 2
            assert exchange(process, "W 56 1 15")[0] == 0
            assert exchange(process, "I 10000")[1] == 1
            assert exchange(process, "R 156")[1] == 1
            assert exchange(process, "R 160")[1] == 0
            assert exchange(process, "W 164 1 15")[0] == 0
            assert exchange(process, "I 0")[1] == 0
            assert process.stdin is not None
            process.stdin.write("Q\n")
            process.stdin.flush()
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def drain_capture(
    process: subprocess.Popen[str], read_ticks: list[int]
) -> list[tuple[int, int, int]]:
    """Drain actual FIFO words and compare immutable sample edge observations.

    Parameters
    ----------
    process
        Production top process after four accepted controller commands.
    read_ticks
        Original sample-read edge snapshots obtained through capture registers.

    Returns
    -------
    list of tuple
        Actual event code, cycle and capture ticks.
    """
    assert exchange(process, "I 1000000")[1] == 1
    assert exchange(process, "R 4")[1] & 4
    records = []
    for _ in range(16):
        assert exchange(process, "R 144")[1] & 1
        words = [exchange(process, f"R {address}")[1] for address in (128, 132, 136, 140)]
        records.append((words[0], words[1], words[2] | (words[3] << 32)))
        assert exchange(process, "W 148 1 15")[0] == 0
    assert exchange(process, "R 144")[1] == 12
    assert [record[0] for record in records] == [1, 2, 3, 4] * 4
    assert [record[1] for record in records] == [cycle for cycle in range(4) for _ in range(4)]
    assert [record[2] for record in records if record[0] == 2] == read_ticks
    assert all(records[index + 4][2] - records[index][2] == 32768 for index in (0, 3, 4, 7, 8, 11))
    return records


@pytest.mark.parametrize("mode", ["pid", "lqr"])
def test_native_feedback_and_capture(
    simulator: Path, native_controllers: tuple[Path, Path], mode: str
) -> None:
    """Apply native commands to actual AXI plant feedback and verify capture edges.

    Parameters
    ----------
    simulator
        Actual selected plant simulation.
    native_controllers
        Real C and Rust public streaming controller programs.
    mode
        PID or LQR recurrence.
    """
    histories = []
    for controller in native_controllers:
        with (
            subprocess.Popen(
                [str(simulator)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
            ) as process,
            subprocess.Popen(
                [str(controller), mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
            ) as kernel,
        ):
            try:
                assert kernel.stdin is not None
                assert kernel.stdout is not None
                kernel.stdin.write(",".join(map(str, DEFAULT)) + "\n")
                kernel.stdin.flush()
                assert exchange(process, "W 60 3 15")[0] == 0
                assert exchange(process, "W 56 1 15")[0] == 0
                samples, commands, read_ticks = [], [], []
                for cycle in range(4):
                    assert exchange(process, "I 1000000")[1] == 1
                    assert exchange(process, "R 156")[1] == cycle + 1
                    position = exchange(process, "R 0")[1]
                    assert exchange(process, "R 16")[1] == cycle
                    velocity = exchange(process, "R 20")[1]
                    reference = exchange(process, "R 24")[1]
                    low = exchange(process, "R 28")[1]
                    high = exchange(process, "R 32")[1]
                    read_ticks.append(low | (high << 32))
                    signed = [
                        value if value < 1 << 31 else value - (1 << 32)
                        for value in (reference, position, velocity)
                    ]
                    row = ",".join(map(str, [cycle, *signed]))
                    samples.append(row)
                    kernel.stdin.write(row + "\n")
                    kernel.stdin.flush()
                    assert select.select([kernel.stdout], [], [], 5)[0]
                    command = kernel.stdout.readline()
                    commands.append(command)
                    raw = int(command.split(",")[1]) & 0xFFFFFFFF
                    assert exchange(process, f"W 40 {cycle} 15")[0] == 0
                    assert exchange(process, f"W 44 {raw} 15")[0] == 0
                    assert exchange(process, "W 48 1 15")[0] == 0
                    assert exchange(process, "W 164 1 15")[0] == 0
                records = drain_capture(process, read_ticks)
                assert "".join(commands) == oracle(mode, DEFAULT, samples)
                histories.append((samples, commands, records))
                kernel.stdin.close()
                assert kernel.wait(timeout=5) == 0
                assert process.stdin is not None
                process.stdin.write("Q\n")
                process.stdin.flush()
                assert process.wait(timeout=5) == 0
            finally:
                for child in (process, kernel):
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=5)
    assert histories[0] == histories[1]


@pytest.mark.parametrize(
    "message",
    [
        "R -1",
        "R 256",
        "R 0 extra",
        "R",
        "W 0 4294967296 15",
        "W 0 1 16",
        "W 0 1",
        "T 10000001",
        "I -1",
        "T 18446744073709551616",
        "Q extra",
        "",
        "X",
    ],
)
def test_protocol_refusal(simulator: Path, message: str) -> None:
    """Reject malformed process requests instead of performing a narrowed access.

    Parameters
    ----------
    simulator
        Real process transport executable.
    message
        Invalid public input record.
    """
    result = subprocess.run(
        [str(simulator)],
        input=message + "\n",
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr
