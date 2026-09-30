# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original native run configuration admission for target firmware

"""Preserve the repository amp_run_input entry point using the installed package."""

from loop_timing_witness.amp_run_input import (
    COEFFICIENT_END,
    COEFFICIENT_START,
    FAULT_INDEX,
    MAX_PHASE,
    MAX_REFERENCE_MODE,
    TOKEN_COUNT,
    read_amp_run,
)

__all__ = [
    "COEFFICIENT_END",
    "COEFFICIENT_START",
    "FAULT_INDEX",
    "MAX_PHASE",
    "MAX_REFERENCE_MODE",
    "TOKEN_COUNT",
    "read_amp_run",
]
