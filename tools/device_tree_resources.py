# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original device-tree register and bus address translation

"""Preserve the repository device_tree_resources entry point using the installed package."""

from loop_timing_witness.device_tree_resources import (
    MAX_ADDRESS_CELLS,
    Region,
    property_cells,
    register_regions,
)

__all__ = [
    "MAX_ADDRESS_CELLS",
    "Region",
    "property_cells",
    "register_regions",
]
