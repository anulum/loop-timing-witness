# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — observed dedicated-hart capture to run-analysis manifest

"""Preserve the repository amp_simulation_manifest entry point using the installed package."""

from loop_timing_witness.amp_simulation_manifest import (
    COEFFICIENT_NAMES,
    ROOT,
    admitted_capture,
    compiler_libraries,
    write_amp_manifest,
)

__all__ = [
    "COEFFICIENT_NAMES",
    "ROOT",
    "admitted_capture",
    "compiler_libraries",
    "write_amp_manifest",
]
