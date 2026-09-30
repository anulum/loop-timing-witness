# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — offline original firmware contract reconciliation

"""Preserve the repository amp_image_receipt entry point using the installed package."""

from loop_timing_witness.amp_image_receipt import (
    MAILBOX_BYTES,
    OPTIONS,
    PREFIX_SIZE,
    recorded_request,
    validate_image_receipt,
)

__all__ = [
    "MAILBOX_BYTES",
    "OPTIONS",
    "PREFIX_SIZE",
    "recorded_request",
    "validate_image_receipt",
]
