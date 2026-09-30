# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ELF section and global symbol refusal tests

"""Corrupt original compiler-emitted ELF section and symbol identities through public admission."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest
from amp_elf_symbols import read_symbols
from amp_image_contract import admit_image_contract
from test_amp_contract import RUN
from test_amp_image_contract import native_image
from test_device_tree_resources import compile_tree

if TYPE_CHECKING:
    from amp_platform import AmpPlatform

__all__ = ["compile_tree", "native_image"]
HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
SECTION = struct.Struct("<IIQQQQIIQQ")
SYMBOL = struct.Struct("<IBBHQQ")


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        (6, 0, "section table geometry"),
        (11, 63, "section table geometry"),
        (12, 0, "section table geometry"),
        (12, 65535, "section table geometry"),
    ],
)
def test_original_section_geometry(
    native_image: tuple[bytes, AmpPlatform], field: int, value: int, finding: str
) -> None:
    """Refuse original section table fields corrupted after genuine linking.

    Parameters
    ----------
    native_image
        Original whole compiled image.
    field
        Header field to alter.
    value
        Invalid original field replacement.
    finding
        Required public refusal diagnostic.
    """
    content, _ = native_image
    fields = list(HEADER.unpack_from(content))
    fields[field] = value
    altered = bytearray(content)
    HEADER.pack_into(altered, 0, *fields)
    with pytest.raises(ValueError, match=finding):
        read_symbols(bytes(altered))


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        (1, 0, "one original symbol table"),
        (4, 1 << 63, "file extent"),
        (5, 0, "symbol table geometry"),
        (5, 1, "symbol table geometry"),
        (6, 65535, "string link"),
        (6, 0, "string link"),
        (9, 23, "symbol table geometry"),
    ],
)
def test_original_symbol_table_geometry(
    native_image: tuple[bytes, AmpPlatform], field: int, value: int, finding: str
) -> None:
    """Reject corrupted original symbol-table extents and linked string identity.

    Parameters
    ----------
    native_image
        Original complete target image.
    field
        Original section field to alter.
    value
        Invalid original field replacement.
    finding
        Required public refusal.
    """
    content, _ = native_image
    header = HEADER.unpack_from(content)
    offset = int(header[6])
    while SECTION.unpack_from(content, offset)[1] != 2:
        offset += SECTION.size
    fields = list(SECTION.unpack_from(content, offset))
    fields[field] = value
    altered = bytearray(content)
    SECTION.pack_into(altered, offset, *fields)
    with pytest.raises(ValueError, match=finding):
        read_symbols(bytes(altered))


@pytest.mark.parametrize(
    ("name", "field", "value", "finding"),
    [
        ("witness_amp_platform", 5, 55, "readonly original object"),
        ("witness_amp_platform", 1, 18, "readonly original object"),
        ("witness_amp_platform", 4, 0x80040000, "readonly original object"),
        ("witness_amp_main", 1, 17, "executable bytes"),
        ("witness_amp_main", 5, 0, "executable bytes"),
        ("witness_amp_main", 4, 0x80040000, "executable bytes"),
        ("_start", 4, 0x80000004, "misplaced"),
        ("__bss_end", 4, 0x80000001, "stack geometry"),
        ("witness_amp_run", 0, 0, "empty, undefined"),
        ("witness_amp_run", 0, 0xFFFFFFFF, "outside the original"),
        ("witness_amp_run", 3, 0, "empty, undefined"),
        ("witness_amp_run", 3, 65535, "invalid section"),
    ],
)
def test_original_symbol_contract_corruption(
    native_image: tuple[bytes, AmpPlatform], name: str, field: int, value: int, finding: str
) -> None:
    """Refuse corrupted original definition geometry through full image admission.

    Parameters
    ----------
    native_image
        Original complete target image and platform.
    name
        Original defined symbol to corrupt.
    field
        Original symbol field index.
    value
        Invalid field replacement.
    finding
        Required refusal diagnostic.
    """
    content, platform = native_image
    header = HEADER.unpack_from(content)
    sections = [
        SECTION.unpack_from(content, int(header[6]) + i * SECTION.size)
        for i in range(int(header[12]))
    ]
    table = next(section for section in sections if section[1] == 2)
    strings = sections[table[6]]
    names = content[strings[4] : strings[4] + strings[5]]
    altered = bytearray(content)
    for offset in range(table[4], table[4] + table[5], SYMBOL.size):
        fields = list(SYMBOL.unpack_from(content, offset))
        if names[fields[0] : names.find(b"\0", fields[0])].decode("ascii") == name:
            fields[field] = value
            SYMBOL.pack_into(altered, offset, *fields)
            break
    else:
        pytest.fail("original compiler did not emit expected symbol")
    with pytest.raises(ValueError, match=finding):
        admit_image_contract(bytes(altered), platform, RUN, 16384)


def test_truncated_symbol_image(native_image: tuple[bytes, AmpPlatform]) -> None:
    """Refuse incomplete original symbol headers without partial interpretation.

    Parameters
    ----------
    native_image
        Original compiler-produced target bytes.
    """
    content, _ = native_image
    with pytest.raises(ValueError, match="image size"):
        read_symbols(content[:63])


@pytest.mark.parametrize("corruption", ["nonascii", "duplicate", "missing"])
def test_original_global_identity(native_image: tuple[bytes, AmpPlatform], corruption: str) -> None:
    """Refuse ambiguous names, non-ASCII original names and missing required globals.

    Parameters
    ----------
    native_image
        Original complete compiler-produced target and platform.
    corruption
        Original symbol identity corruption to introduce.
    """
    content, platform = native_image
    header = HEADER.unpack_from(content)
    sections = [
        SECTION.unpack_from(content, int(header[6]) + i * SECTION.size)
        for i in range(int(header[12]))
    ]
    table = next(section for section in sections if section[1] == 2)
    strings = sections[table[6]]
    names = content[strings[4] : strings[4] + strings[5]]
    altered = bytearray(content)
    for offset in range(table[4], table[4] + table[5], SYMBOL.size):
        fields = list(SYMBOL.unpack_from(content, offset))
        if names[fields[0] : names.find(b"\0", fields[0])].decode("ascii") != "witness_amp_run":
            continue
        if corruption == "nonascii":
            altered[strings[4] + fields[0]] = 255
            finding = "not ASCII"
        elif corruption == "duplicate":
            fields[0] = names.index(b"witness_amp_platform\0")
            SYMBOL.pack_into(altered, offset, *fields)
            finding = "ambiguous"
        else:
            fields[1] = 1
            SYMBOL.pack_into(altered, offset, *fields)
            finding = "required entry/resource symbols"
        break
    else:
        pytest.fail("original compiler did not emit expected global")
    with pytest.raises(ValueError, match=finding):
        admit_image_contract(bytes(altered), platform, RUN, 16384)
