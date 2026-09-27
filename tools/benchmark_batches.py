# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native benchmark batch protocol and statistics

"""Validate real native batches and summarize measured batch-average timings."""

from __future__ import annotations

import statistics

ITERATIONS = 1_000_000
MIN_REPEATS = 5


def benchmark_statistics(samples: list[int]) -> dict[str, float]:
    """Summarize native million-step batch means, not individual-step latency.

    Parameters
    ----------
    samples
        Positive elapsed nanoseconds for at least five complete native batches.

    Returns
    -------
    dict of str to float
        Per-step batch-average nanoseconds and reciprocal mean throughput.
    """
    if len(samples) < MIN_REPEATS or any(sample <= 0 for sample in samples):
        message = "benchmark statistics require five positive elapsed samples"
        raise ValueError(message)
    values = [sample / ITERATIONS for sample in samples]
    percentiles = statistics.quantiles(values, n=100, method="inclusive")
    average = statistics.mean(values)
    return {
        "p50_ns": statistics.median(values),
        "p95_ns": percentiles[94],
        "p99_ns": percentiles[98],
        "mean_ns": average,
        "min_ns": min(values),
        "max_ns": max(values),
        "throughput_steps_per_second": 1e9 / average,
    }


def decode_batch(content: str) -> list[tuple[str, int, int, int]]:
    """Validate the actual native benchmark's two-controller batch protocol.

    Parameters
    ----------
    content
        Captured native standard output.

    Returns
    -------
    list of tuple
        Controller, iteration count, elapsed nanoseconds and command checksum.

    Raises
    ------
    ValueError
        If row order, field count or numeric bounds disagree with the protocol.
    """
    decoded = [line.split(",") for line in content.splitlines()]
    controllers = ["pid", "lqr"]
    if len(decoded) != len(controllers) or [row[0] for row in decoded] != controllers:
        message = "native benchmark must emit PID and LQR rows"
        raise ValueError(message)
    result = []
    field_count = 4
    for fields in decoded:
        if len(fields) != field_count:
            message = "native benchmark row must have four fields"
            raise ValueError(message)
        iterations, elapsed, checksum = map(int, fields[1:])
        if iterations != ITERATIONS or elapsed <= 0 or checksum < 0:
            message = "invalid native benchmark counts or timing"
            raise ValueError(message)
        result.append((fields[0], iterations, elapsed, checksum))
    return result
