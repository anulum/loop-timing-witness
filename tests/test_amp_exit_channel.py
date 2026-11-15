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
from amp_target import symbol_offset
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
        altered[symbol_offset(segments, symbols["tohost"].address)] = 1
        finding = "cannot be preloaded"
    else:
        assert "tohost" in symbols, "original compiler did not emit HTIF symbol"
        offset, fields = _global_symbol_record(content, "tohost")
        finding = _damage_symbol_record(fields, corruption, symbols["fromhost"].address)
        SYMBOL.pack_into(altered, offset, *fields)
    with pytest.raises(ValueError, match=finding):
        admit_exit_channel(bytes(altered), segments, isa=True)


def _global_symbol_record(content: bytes, name: str) -> tuple[int, list[int]]:
    """Return the file offset and fields of one global or weak ELF symbol record.

    Parameters
    ----------
    content
        Original ELF image.
    name
        Symbol name.

    Returns
    -------
    tuple[int, list[int]]
        Record offset in the file and its fields in ``SYMBOL`` order.
    """
    header = HEADER.unpack_from(content)
    sections = [
        SECTION.unpack_from(content, int(header[6]) + i * SECTION.size)
        for i in range(int(header[12]))
    ]
    table = next(section for section in sections if section[1] == 2)
    strings = sections[table[6]]
    names = content[strings[4] : strings[4] + strings[5]]
    records = {
        offset: SYMBOL.unpack_from(content, offset)
        for offset in range(table[4], table[4] + table[5], SYMBOL.size)
    }
    globals_by_name = {
        names[fields[0] : names.find(b"\0", fields[0])].decode("ascii"): offset
        for offset, fields in records.items()
        if fields[1] >> 4 in (1, 2)
    }
    offset = globals_by_name[name]
    return offset, list(records[offset])


def _damage_symbol_record(fields: list[int], corruption: str, fromhost: int) -> str:
    """Damage the HTIF completion symbol record in place.

    Parameters
    ----------
    fields
        ``tohost`` record fields, changed in place.
    corruption
        Exact record corruption.
    fromhost
        Address of the original ``fromhost`` symbol.

    Returns
    -------
    str
        Required refusal text.
    """
    if corruption == "missing":
        fields[1] = 1
        return "requires both"
    if corruption == "kind":
        fields[1] = 18
    elif corruption == "size":
        fields[5] = 16
    elif corruption == "alignment":
        fields[4] += 1
    elif corruption == "outside":
        fields[4] = 0x80040000
    else:
        fields[4] = fromhost
        return "distinct original"
    return "aligned writable"
