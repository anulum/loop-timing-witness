# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original bounded ELF symbol and string table decoding

"""Preserve the repository amp_elf_symbols entry point using the installed package."""

from loop_timing_witness.amp_elf_symbols import (
    ABSOLUTE_SECTION,
    GLOBAL_BINDING,
    MAX_SECTIONS,
    NO_BITS,
    SECTION,
    STRING_TABLE,
    SYMBOL,
    SYMBOL_TABLE,
    WEAK_BINDING,
    ElfSymbol,
    read_symbols,
)

__all__ = [
    "ABSOLUTE_SECTION",
    "GLOBAL_BINDING",
    "MAX_SECTIONS",
    "NO_BITS",
    "SECTION",
    "STRING_TABLE",
    "SYMBOL",
    "SYMBOL_TABLE",
    "WEAK_BINDING",
    "ElfSymbol",
    "read_symbols",
]
