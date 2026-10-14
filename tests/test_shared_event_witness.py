# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared-counter witness public-port simulations

"""Check simultaneous channel timestamps, isolated loss and reset through real RTL."""

from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("overflow", "counter_bits", "drain_period", "count"),
    [(0, 32, 7, 4), (1, 3, 3, 4), (0, 32, 7, 1000)],
)
def test_parallel_capture_shared_ticks_and_independent_loss(
    tmp_path: Path, overflow: int, counter_bits: int, drain_period: int, count: int
) -> None:
    """Compile actual capture/FIFO RTL and verify every exported record.

    Parameters
    ----------
    tmp_path
        Isolated compiler and raw-stream allocation.
    overflow
        Select lossless markers or isolated full-buffer traffic.
    counter_bits
        Native drop-counter width, including a genuine saturating run.
    drain_period
        Half-period of the independent drain clock, in simulator time units.
    count
        Four sparse records or a whole 1,000-record continuous capture before drain.
    """
    repository = Path(__file__).resolve().parents[1]
    binary = tmp_path / "shared-event-witness.vvp"
    sources = [
        "rtl/clock_reset_release.sv",
        "rtl/event_record_fifo.sv",
        "rtl/shared_event_witness.sv",
        "tests/rtl/shared_event_witness_tb.sv",
    ]
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "shared_event_witness_tb",
            "-o",
            str(binary),
            f"-Pshared_event_witness_tb.OVERFLOW_RUN={overflow}",
            f"-Pshared_event_witness_tb.OVERFLOW_COUNTER_BITS={counter_bits}",
            f"-Pshared_event_witness_tb.DRAIN_HALF_PERIOD={drain_period}",
            f"-Pshared_event_witness_tb.NORMAL_COUNT={count}",
            f"-Pshared_event_witness_tb.ADDRESS_BITS={10 if count == 1000 else 3}",
            *(str(repository / source) for source in sources),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    result = subprocess.run(
        ["vvp", str(binary), f"+EVENT_DIRECTORY={tmp_path}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SHARED_CAPTURE_PASS reset_pass=1" in result.stdout
    records = [
        list(struct.iter_unpack("<BBHIQ", (tmp_path / f"channel-{channel}.bin").read_bytes()))
        for channel in range(3)
    ]
    if not overflow:
        assert records[0] == records[1] == records[2]
        spacing = 1 if count == 1000 else 3
        assert records[0] == [
            (17, 0, 0, 0, 10),
            *((14, 0, 0, index, 20 + spacing * index) for index in range(count)),
            (17, 0, 0, 1, 1030 if count == 1000 else 40),
        ]
    else:
        assert len(records[0]) == 8
        assert len(records[1]) == 25
        assert records[2] == []
        assert [record[3] for record in records[0]] == list(range(8))
        assert [record[3] for record in records[1]] == list(range(25))
        assert [record[4] for record in records[0]] == [record[4] for record in records[1][:8]]
        assert all(record[0] == 14 and record[1:3] == (0, 0) for record in records[0])
        assert all(record[0] == 15 and record[1:3] == (0, 0) for record in records[1])


@pytest.mark.parametrize(
    ("parameter", "value", "message"),
    [
        ("CHANNEL_COUNT", 0, "CHANNEL_COUNT must be in [1,32]"),
        ("CHANNEL_COUNT", 33, "CHANNEL_COUNT must be in [1,32]"),
        ("OVERFLOW_COUNTER_BITS", 0, "OVERFLOW_COUNTER_BITS must be in [1,32]"),
        ("OVERFLOW_COUNTER_BITS", 33, "OVERFLOW_COUNTER_BITS must be in [1,32]"),
        ("ADDRESS_BITS", 0, "ADDRESS_BITS must be in [1,14]"),
        ("ADDRESS_BITS", 15, "ADDRESS_BITS must be in [1,14]"),
    ],
)
def test_shared_capture_refuses_invalid_parameters(
    tmp_path: Path, parameter: str, value: int, message: str
) -> None:
    """Reject unsupported channel and counter widths at the actual RTL entry.

    Parameters
    ----------
    tmp_path
        Isolated compiler-output allocation.
    parameter
        Public module parameter being overridden.
    value
        Unsupported boundary value.
    message
        Exact authored configuration refusal.
    """
    repository = Path(__file__).resolve().parents[1]
    binary = tmp_path / "invalid-shared-capture.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "shared_event_witness",
            "-o",
            str(binary),
            f"-Pshared_event_witness.{parameter}={value}",
            str(repository / "rtl/clock_reset_release.sv"),
            str(repository / "rtl/event_record_fifo.sv"),
            str(repository / "rtl/shared_event_witness.sv"),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    result = subprocess.run(
        ["vvp", str(binary)], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode != 0
    assert message in result.stdout


def test_shared_capture_synthesis_preserves_counter_and_independent_memories(
    tmp_path: Path,
) -> None:
    """Check the real synthesised timebase driver and all default FIFO memories.

    Parameters
    ----------
    tmp_path
        Isolated synthesis netlist allocation.
    """
    repository = Path(__file__).resolve().parents[1]
    netlist = tmp_path / "shared-capture.json"
    script = (
        "read_verilog -sv rtl/clock_reset_release.sv rtl/event_record_fifo.sv "
        "rtl/shared_event_witness.sv; hierarchy -check -top shared_event_witness; "
        f"proc; opt; memory_dff; memory_collect; write_json {json.dumps(str(netlist))}"
    )
    subprocess.run(
        ["yosys", "-Q", "-T", "-p", script],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    design = json.loads(netlist.read_text(encoding="utf-8"))
    top = design["modules"]["shared_event_witness"]
    tick_bits = top["ports"]["counter_ticks"]["bits"]
    tick_drivers = [
        cell for cell in top["cells"].values() if cell["connections"].get("Q") == tick_bits
    ]
    assert len(tick_bits) == 64
    assert len(tick_drivers) == 1
    assert tick_drivers[0]["type"] == "$adff"
    instances = [cell for cell in top["cells"].values() if "event_record_fifo" in cell["type"]]
    assert len(instances) == 3
    for cell in instances:
        memory = [
            item
            for item in design["modules"][cell["type"]]["cells"].values()
            if item["type"] == "$mem_v2"
        ]
        assert len(memory) == 1
        assert int(memory[0]["parameters"]["WIDTH"], 2) == 128
        assert int(memory[0]["parameters"]["SIZE"], 2) == 1024
