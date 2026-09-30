# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable native firmware run and platform contract generation

"""Preserve the repository amp_contract entry point using the installed package."""

from loop_timing_witness.amp_contract import (
    COEFFICIENT_COUNT,
    INT32_MAX,
    INT32_MIN,
    MAX_DURATION_TICKS,
    MAX_OVERLOAD_ITERATIONS,
    SCALE,
    UINT32_MAX,
    AmpRun,
    render_contract,
)

__all__ = [
    "COEFFICIENT_COUNT",
    "INT32_MAX",
    "INT32_MIN",
    "MAX_DURATION_TICKS",
    "MAX_OVERLOAD_ITERATIONS",
    "SCALE",
    "UINT32_MAX",
    "AmpRun",
    "render_contract",
]
