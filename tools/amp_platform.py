# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original AMP platform resource admission

"""Preserve the repository amp_platform entry point using the installed package."""

from loop_timing_witness.amp_platform import (
    AmpPlatform,
    bind_platform,
)

__all__ = [
    "AmpPlatform",
    "bind_platform",
]
