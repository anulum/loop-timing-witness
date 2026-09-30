# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — admitted binary device-tree blocks and memory reservations

"""Preserve the repository device_tree_blob entry point using the installed package."""

from loop_timing_witness.device_tree_blob import (
    ADDRESS_LIMIT,
    HEADER_SIZE,
    MAGIC,
    MAX_BLOB_BYTES,
    RESERVATION_ALIGNMENT,
    RESERVATION_SIZE,
    VERSION,
    WORD_BYTES,
    DeviceTree,
    decode_device_tree,
)

__all__ = [
    "ADDRESS_LIMIT",
    "HEADER_SIZE",
    "MAGIC",
    "MAX_BLOB_BYTES",
    "RESERVATION_ALIGNMENT",
    "RESERVATION_SIZE",
    "VERSION",
    "WORD_BYTES",
    "DeviceTree",
    "decode_device_tree",
]
