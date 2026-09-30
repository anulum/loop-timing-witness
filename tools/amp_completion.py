# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP logger completion and captured stream agreement

"""Preserve the repository amp_completion entry point using the installed package."""

from loop_timing_witness.amp_completion import (
    FIELDS,
    PREFIX,
    AmpCompletion,
    completion_receipt,
    decode_completion,
    validate_capture,
)

__all__ = [
    "FIELDS",
    "PREFIX",
    "AmpCompletion",
    "completion_receipt",
    "decode_completion",
    "validate_capture",
]
