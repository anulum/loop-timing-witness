# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host load receipt validation and report custody

"""Preserve the repository host_load_receipt entry point using the installed package."""

from loop_timing_witness.host_load_receipt import (
    MAX_DATAGRAM_BYTES,
    ROOT,
    attach_host_load,
    validate_host_load,
)

__all__ = [
    "MAX_DATAGRAM_BYTES",
    "ROOT",
    "attach_host_load",
    "validate_host_load",
]
