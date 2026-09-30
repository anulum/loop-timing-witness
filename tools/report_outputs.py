# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — atomic host report outputs

"""Preserve the repository report_outputs entry point using the installed package."""

from loop_timing_witness.report_outputs import (
    write_report,
)

__all__ = [
    "write_report",
]
