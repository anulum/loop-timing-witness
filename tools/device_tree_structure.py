# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded flattened device-tree structure decoding

"""Preserve the repository device_tree_structure entry point using the installed package."""

from loop_timing_witness.device_tree_structure import (
    ALIGNMENT,
    MAX_DEPTH,
    MAX_NODES,
    MAX_PATH_CHARACTERS,
    PROPERTY,
    WORD,
    Node,
    Token,
    aligned_offset,
    decode_structure,
    terminated_string,
)

__all__ = [
    "ALIGNMENT",
    "MAX_DEPTH",
    "MAX_NODES",
    "MAX_PATH_CHARACTERS",
    "PROPERTY",
    "WORD",
    "Node",
    "Token",
    "aligned_offset",
    "decode_structure",
    "terminated_string",
]
