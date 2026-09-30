# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — board-facing AXI4-Lite witness simulation

"""Exercise the board-facing AXI4-Lite boundary through production RTL."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from conftest import RunRtl


@pytest.mark.parametrize("thermal", [0, 1])
def test_icicle_witness_registers_and_irq(thermal: int, run_rtl: RunRtl) -> None:
    """Reach register and interrupt behavior through the 38-bit FIC address port.

    Parameters
    ----------
    thermal
        Mechanical or thermal plant selection.
    run_rtl
        Real Icarus compilation and execution fixture.
    """
    result = run_rtl("icicle_witness_tb", {"THERMAL": thermal}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"ICICLE_WITNESS_PASS thermal={thermal}" in result.stdout
