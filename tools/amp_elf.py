# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded original RV64 executable load-segment admission

"""Preserve the repository amp_elf entry point using the installed package."""

from loop_timing_witness.amp_elf import (
    ADDRESS_LIMIT,
    ELF_HEADER,
    EXECUTABLE_TYPE,
    FORBIDDEN_TYPES,
    LOAD_TYPE,
    MAX_IMAGE_BYTES,
    MAX_PROGRAM_HEADERS,
    PAGE_BYTES,
    PROGRAM_HEADER,
    READ_EXECUTE,
    READ_WRITE,
    RV64_MACHINE,
    RVC_FLAG,
    LoadSegment,
    admit_elf,
)

__all__ = [
    "ADDRESS_LIMIT",
    "ELF_HEADER",
    "EXECUTABLE_TYPE",
    "FORBIDDEN_TYPES",
    "LOAD_TYPE",
    "MAX_IMAGE_BYTES",
    "MAX_PROGRAM_HEADERS",
    "PAGE_BYTES",
    "PROGRAM_HEADER",
    "READ_EXECUTE",
    "READ_WRITE",
    "RV64_MACHINE",
    "RVC_FLAG",
    "LoadSegment",
    "admit_elf",
]
