# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dual-clock FIFO simulation tests

"""Exercise the record FIFO through independently clocked public ports."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

import pytest

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize(
    ("address_bits", "write_half", "read_half"),
    [(1, 3, 7), (2, 7, 3), (4, 5, 5), (14, 3, 7)],
)
def test_fifo_capacity_wrap_clocks_and_queued_reset(
    address_bits: int,
    write_half: int,
    read_half: int,
    run_rtl: RunRtl,
) -> None:
    """Preserve every accepted record across full, empty, wrap and reset.

    Parameters
    ----------
    address_bits
        FIFO capacity exponent, including the configured 16,384 records.
    write_half
        Write clock half period in simulation nanoseconds.
    read_half
        Read clock half period in simulation nanoseconds.
    run_rtl
        Real Icarus compiler and simulator runner.
    """
    result = run_rtl(
        "event_record_fifo_tb",
        {
            "ADDRESS_BITS": address_bits,
            "WRITE_HALF": write_half,
            "READ_HALF": read_half,
        },
        [],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"FIFO_PASS depth={1 << address_bits}" in result.stdout
