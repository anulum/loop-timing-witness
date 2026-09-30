# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host run analysis command

"""Preserve the repository analyze_run entry point using the installed package."""

import sys

from loop_timing_witness.analyze_run import (
    REPORT_SCHEMA,
    build_report,
    main,
)

__all__ = [
    "REPORT_SCHEMA",
    "build_report",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
