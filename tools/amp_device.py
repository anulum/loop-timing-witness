# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original AXI aperture and retained interrupt resource binding

"""Preserve the repository amp_device entry point using the installed package."""

from loop_timing_witness.amp_device import (
    APERTURE_BYTES,
    COMPATIBLE,
    EXTENDED_INTERRUPT_CELLS,
    WitnessDevice,
    bind_device,
)

__all__ = [
    "APERTURE_BYTES",
    "COMPATIBLE",
    "EXTENDED_INTERRUPT_CELLS",
    "WitnessDevice",
    "bind_device",
]
