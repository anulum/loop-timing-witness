# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — event statistics

"""Preserve the repository run_analysis entry point using the installed package."""

from loop_timing_witness.run_analysis import (
    analyse_events,
    distribution,
)

__all__ = [
    "analyse_events",
    "distribution",
]
