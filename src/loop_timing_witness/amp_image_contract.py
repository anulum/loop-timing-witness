# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original compiled contract bytes and stack ownership admission

"""Compare actual linked constants and integer stack against admitted platform inputs."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from .amp_elf import PAGE_BYTES, READ_EXECUTE, READ_WRITE, LoadSegment, admit_elf
from .amp_elf_symbols import ElfSymbol, read_symbols

if TYPE_CHECKING:
    from .amp_contract import AmpRun
    from .amp_platform import AmpPlatform

PLATFORM_BYTES = struct.Struct("<II6Q")
RUN_BYTES = struct.Struct("<4I11i")
FUNCTION_KIND = 2
OBJECT_KIND = 1
STACK_ALIGNMENT = 16
BSS_ALIGNMENT = 8


def _constant(
    content: bytes, segments: tuple[LoadSegment, ...], symbol: ElfSymbol, expected: bytes
) -> None:
    """Require one original const object entirely backed by RX file bytes matching the contract.

    Parameters
    ----------
    content
        Original linked executable.
    segments
        Admitted original load segments.
    symbol
        Original global object symbol.
    expected
        Exact native ABI bytes derived from admitted inputs.

    Raises
    ------
    ValueError
        If type, size, storage permissions or original initialized bytes differ.
    """
    owners = [
        segment
        for segment in segments
        if segment.flags == READ_EXECUTE
        and segment.address <= symbol.address
        and symbol.address + symbol.size <= segment.address + segment.file_bytes
    ]
    if symbol.kind != OBJECT_KIND or symbol.size != len(expected) or len(owners) != 1:
        message = "compiled AMP contract is not one complete readonly original object"
        raise ValueError(message)
    offset = owners[0].offset + symbol.address - owners[0].address
    if content[offset : offset + symbol.size] != expected:
        message = "compiled AMP contract bytes differ from admitted platform/run inputs"
        raise ValueError(message)


def admit_image_contract(
    content: bytes, platform: AmpPlatform, run: AmpRun, stack_bytes: int
) -> tuple[LoadSegment, ...]:
    """Admit actual native constants, required controller entry points and complete stack geometry.

    Parameters
    ----------
    content
        Complete original linked ELF firmware.
    platform
        Original admitted topology resources.
    run
        Validated immutable native run.
    stack_bytes
        Explicit original stack allocation passed to the production linker.

    Returns
    -------
    tuple of LoadSegment
        Original fully bounded load segments after native contract admission.

    Raises
    ------
    ValueError
        If original symbols, entry points, initialized constants or stack ownership differ.
    """
    segments = admit_elf(content, platform.memory.firmware)
    symbols = read_symbols(content)
    required = (
        "_start",
        "witness_amp_main",
        "witness_amp_trap",
        "witness_amp_exit",
        "witness_amp_platform",
        "witness_amp_run",
        "__bss_start",
        "__bss_end",
        "__stack_top",
    )
    if (
        any(name not in symbols for name in required)
        or symbols["_start"].address != platform.memory.firmware.address
    ):
        message = "firmware original required entry/resource symbols are absent or misplaced"
        raise ValueError(message)
    for name in ("witness_amp_main", "witness_amp_trap", "witness_amp_exit"):
        symbol = symbols[name]
        if (
            symbol.kind != FUNCTION_KIND
            or not symbol.size
            or not any(
                segment.flags == READ_EXECUTE
                and segment.address <= symbol.address
                and symbol.address + symbol.size <= segment.address + segment.file_bytes
                for segment in segments
            )
        ):
            message = "firmware controller entry point lacks original executable bytes"
            raise ValueError(message)
    device = platform.device
    expected_platform = PLATFORM_BYTES.pack(
        platform.hart,
        platform.source,
        device.aperture.address,
        device.plic.priority,
        device.plic.enable_word,
        device.plic.threshold,
        device.plic.claim,
        platform.memory.shared.address,
    )
    expected_run = RUN_BYTES.pack(
        run.cycles, run.period_ticks, run.lqr, run.overload_iterations, *run.coefficients
    )
    _constant(content, segments, symbols["witness_amp_platform"], expected_platform)
    _constant(content, segments, symbols["witness_amp_run"], expected_run)
    start = symbols["__bss_start"].address
    end = symbols["__bss_end"].address
    top = symbols["__stack_top"].address
    if (
        type(stack_bytes) is not int
        or stack_bytes < PAGE_BYTES
        or stack_bytes % STACK_ALIGNMENT
        or start % BSS_ALIGNMENT
        or end % BSS_ALIGNMENT
        or end < start
        or top != (end + STACK_ALIGNMENT - 1) // STACK_ALIGNMENT * STACK_ALIGNMENT + stack_bytes
        or not any(
            segment.flags == READ_WRITE
            and segment.address <= start
            and top <= segment.address + segment.memory_bytes
            for segment in segments
        )
    ):
        message = "firmware original BSS and integer stack geometry differs from the reservation"
        raise ValueError(message)
    return segments
