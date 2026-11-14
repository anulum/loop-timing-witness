# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — declared service stimulus of the closed-loop benchmark harness

"""Declare every input of one closed-loop harness run and the counts it must produce.

The harness clocks the production ``control_plant_witness`` at the minimum declared
period. A simulated service reads each sample and writes each command at offsets drawn
from a seeded SplitMix64 sequence, computing the command with the production C PID kernel.
The offsets are a declared stimulus, not processor execution time. One write in every
``SKIP_INTERVAL`` cycles is withheld, which produces a single deadline miss below the trip
limit. One delay fault of ``FAULT_PERIODS`` periods, ``FAULT_LEAD`` cycles before the end,
trips the deadline monitor, so the final cycles run in the safe state.
"""

from __future__ import annotations

from typing import Final

from loop_timing_witness.amp_simulation_manifest import COEFFICIENT_NAMES

SCALE: Final = 1 << 24
PERIOD_TICKS: Final = 5000
MISS_LIMIT: Final = 3
FIFO_ADDRESS_BITS: Final = 14
FAULT_LEAD: Final = 8
FAULT_PERIODS: Final = 3
SKIP_INTERVAL: Final = 97
MINIMUM_CYCLES: Final = 16
MAXIMUM_CYCLES: Final = (1 << 32) - 1
MAXIMUM_SEED: Final = (1 << 63) - 1
SCHEMA: Final = "loop-timing-witness.closed-loop-stimulus.v1"
COEFFICIENTS: Final = dict(
    zip(
        COEFFICIENT_NAMES,
        (
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
        ),
        strict=True,
    )
)
SERVICE: Final = {"read_min": 10, "read_span": 190, "gap_min": 20, "gap_span": 780, "drain_half": 3}
REFERENCE: Final = {"reference_mode": 0, "phase_increment": 1, "reference_amplitude": SCALE}


def harness_arguments(cycles: int, seed: int) -> dict[str, int]:
    """Return the complete harness argument set for one run.

    Parameters
    ----------
    cycles
        Control cycles, at least ``MINIMUM_CYCLES``.
    seed
        Seed of the service offset sequence.

    Returns
    -------
    dict[str, int]
        Every ``key=value`` argument the harness requires, in a stable order.

    Raises
    ------
    ValueError
        If the cycle count or the seed is outside its declared range.
    """
    if not MINIMUM_CYCLES <= cycles <= MAXIMUM_CYCLES:
        message = f"cycles must be in [{MINIMUM_CYCLES}, {MAXIMUM_CYCLES}]"
        raise ValueError(message)
    if not 0 <= seed <= MAXIMUM_SEED:
        message = f"seed must be in [0, {MAXIMUM_SEED}]"
        raise ValueError(message)
    return {
        "cycles": cycles,
        "seed": seed,
        "period": PERIOD_TICKS,
        **SERVICE,
        "skip_interval": SKIP_INTERVAL,
        "fault_cycle": cycles - FAULT_LEAD,
        "fault_periods": FAULT_PERIODS,
        **REFERENCE,
        **COEFFICIENTS,
    }


def expected_counts(cycles: int) -> dict[str, int]:
    """Return the withheld writes and deadline misses the declared stimulus must produce.

    A write is withheld in cycle ``c`` when ``c % SKIP_INTERVAL == SKIP_INTERVAL - 1``
    and the cycle ends at least three cycles before the fault, so no withheld write joins
    the fault's misses. The fault misses ``MISS_LIMIT`` deadlines, which trips the monitor,
    and every later cycle misses its deadline in the safe state.

    Parameters
    ----------
    cycles
        Control cycles of the run.

    Returns
    -------
    dict[str, int]
        ``skipped_writes`` and ``misses``.
    """
    fault = cycles - FAULT_LEAD
    skipped = (fault - 3) // SKIP_INTERVAL
    return {"skipped_writes": skipped, "misses": skipped + cycles - fault}


def declaration(cycles: int, seed: int) -> dict[str, object]:
    """Return the stimulus declaration bound into each run as ``stimulus.json``.

    Parameters
    ----------
    cycles
        Control cycles of the run.
    seed
        Seed of the service offset sequence.

    Returns
    -------
    dict[str, object]
        Schema, harness source, RTL build parameters and the exact harness arguments.
    """
    return {
        "schema": SCHEMA,
        "harness": "benchmarks/closed_loop_harness.cpp",
        "build": {
            "top_module": "control_plant_witness",
            "period_ticks": PERIOD_TICKS,
            "miss_limit": MISS_LIMIT,
            "fifo_address_bits": FIFO_ADDRESS_BITS,
            "thermal": False,
        },
        "service": (
            "Declared stimulus standing in for an interrupt-driven bare-metal service: "
            "read and write offsets from SplitMix64, commands from the production C PID "
            "kernel; not processor execution time."
        ),
        "arguments": harness_arguments(cycles, seed),
    }
