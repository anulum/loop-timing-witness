# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original PLIC machine context and register binding

"""Preserve the repository device_tree_interrupts entry point using the installed package."""

from loop_timing_witness.device_tree_interrupts import (
    BITS_PER_WORD,
    CONTEXT_BASE,
    CONTEXT_STRIDE,
    ENABLE_BASE,
    ENABLE_STRIDE,
    MACHINE_EXTERNAL_IRQ,
    MAX_CONTEXTS,
    MAX_SOURCE,
    MAX_U54_HART,
    UINT32_MAX,
    WORD_BYTES,
    PlicRegisters,
    PlicSelection,
    bind_plic,
)

__all__ = [
    "BITS_PER_WORD",
    "CONTEXT_BASE",
    "CONTEXT_STRIDE",
    "ENABLE_BASE",
    "ENABLE_STRIDE",
    "MACHINE_EXTERNAL_IRQ",
    "MAX_CONTEXTS",
    "MAX_SOURCE",
    "MAX_U54_HART",
    "UINT32_MAX",
    "WORD_BYTES",
    "PlicRegisters",
    "PlicSelection",
    "bind_plic",
]
