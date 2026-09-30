# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual ISA completion channel and preloaded-exit refusal tests

"""Validate actual target completion channels using original whole linked firmware."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_exit_channel import admit_exit_channel
from test_amp_image_contract import native_image
from test_device_tree_resources import compile_tree

if TYPE_CHECKING:
    from amp_platform import AmpPlatform

__all__ = ["compile_tree", "native_image"]
HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION = struct.Struct("<IIQQQQIIQQ")
SYMBOL = struct.Struct("<IBBHQQ")


def test_actual_original_htif(native_image: tuple[bytes, AmpPlatform]) -> None:
    """Admit two actual initialized-zero HTIF words and refuse that image in parked mode.

    Parameters
    ----------
    native_image
        Original complete compiler-produced ISA firmware.
    """
    content, platform = native_image
    segments = admit_elf(content, platform.memory.firmware)
    admit_exit_channel(content, segments, isa=True)
    with pytest.raises(ValueError, match="parked firmware"):
        admit_exit_channel(content, segments, isa=False)


@pytest.mark.parametrize(
    "corruption", ["missing", "kind", "size", "alignment", "outside", "alias", "preloaded"]
)
def test_original_completion_refusals(
    native_image: tuple[bytes, AmpPlatform], corruption: str
) -> None:
    """Refuse damaged original HTIF definitions and target completion preloaded before execution.

    Parameters
    ----------
    native_image
        Original complete cross-compiled firmware.
    corruption
        Exact original completion channel corruption.
    """
    content, platform = native_image
    segments = admit_elf(content, platform.memory.firmware)
    symbols = read_symbols(content)
    altered = bytearray(content)
    if corruption == "preloaded":
        symbol = symbols["tohost"]
        owner = next(
            segment
            for segment in segments
            if segment.address <= symbol.address < segment.address + segment.file_bytes
        )
        altered[owner.offset + symbol.address - owner.address] = 1
        finding = "cannot be preloaded"
    else:
        header = HEADER.unpack_from(content)
        sections = [
            SECTION.unpack_from(content, int(header[6]) + i * SECTION.size)
            for i in range(int(header[12]))
        ]
        table = next(section for section in sections if section[1] == 2)
        strings = sections[table[6]]
        names = content[strings[4] : strings[4] + strings[5]]
        for offset in range(table[4], table[4] + table[5], SYMBOL.size):
            fields = list(SYMBOL.unpack_from(content, offset))
            if names[fields[0] : names.find(b"\0", fields[0])].decode("ascii") != "tohost":
                continue
            if corruption == "missing":
                fields[1] = 1
                finding = "requires both"
            elif corruption == "kind":
                fields[1] = 18
                finding = "aligned writable"
            elif corruption == "size":
                fields[5] = 16
                finding = "aligned writable"
            elif corruption == "alignment":
                fields[4] += 1
                finding = "aligned writable"
            elif corruption == "outside":
                fields[4] = 0x80040000
                finding = "aligned writable"
            else:
                fields[4] = symbols["fromhost"].address
                finding = "distinct original"
            SYMBOL.pack_into(altered, offset, *fields)
            break
        else:
            pytest.fail("original compiler did not emit HTIF symbol")
    with pytest.raises(ValueError, match=finding):
        admit_exit_channel(bytes(altered), segments, isa=True)
