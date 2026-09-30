# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original bounded ELF symbol and string table decoding

"""Decode original defined global RV64 symbols without trusting command text output."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .amp_elf import ELF_HEADER, MAX_IMAGE_BYTES

SECTION = struct.Struct("<IIQQQQIIQQ")
SYMBOL = struct.Struct("<IBBHQQ")
SYMBOL_TABLE = 2
STRING_TABLE = 3
NO_BITS = 8
MAX_SECTIONS = 16384
GLOBAL_BINDING = 1
WEAK_BINDING = 2
ABSOLUTE_SECTION = 0xFFF1


@dataclass(frozen=True)
class ElfSymbol:
    """One original defined global symbol and its section identity.

    Parameters
    ----------
    address
        Original symbol value.
    size
        Original symbol byte extent.
    kind
        Original ELF symbol type.
    section
        Original defining section index or absolute marker.
    """

    address: int
    size: int
    kind: int
    section: int


def _sections(content: bytes) -> list[tuple[int, ...]]:
    """Require bounded original section geometry and every backed file extent.

    Parameters
    ----------
    content
        Complete original ELF image already admitted by the load validator.

    Returns
    -------
    list of tuple
        Original section headers.

    Raises
    ------
    ValueError
        If section geometry or initialized file extents are invalid.
    """
    if not ELF_HEADER.size <= len(content) <= MAX_IMAGE_BYTES:
        message = "firmware symbol image size is outside bounds"
        raise ValueError(message)
    header = ELF_HEADER.unpack_from(content)
    offset, size, count = header[6], header[11], header[12]
    if (
        size != SECTION.size
        or not 1 <= count <= MAX_SECTIONS
        or offset < ELF_HEADER.size
        or offset + count * size > len(content)
    ):
        message = "firmware original section table geometry is invalid"
        raise ValueError(message)
    sections = [SECTION.unpack_from(content, offset + i * size) for i in range(count)]
    if any(
        section[1] != NO_BITS and section[4] + section[5] > len(content) for section in sections
    ):
        message = "firmware original section file extent is truncated"
        raise ValueError(message)
    return sections


def read_symbols(content: bytes) -> dict[str, ElfSymbol]:
    """Require one original symbol table and unique defined global/weak symbol names.

    Parameters
    ----------
    content
        Complete original admitted executable, retaining its original symbol table.

    Returns
    -------
    dict of str to ElfSymbol
        Original defined global and weak symbols without hidden undefined dependencies.

    Raises
    ------
    ValueError
        If tables, strings, symbol geometry, definitions or global identities are invalid.
    """
    sections = _sections(content)
    tables = [section for section in sections if section[1] == SYMBOL_TABLE]
    if len(tables) != 1:
        message = "firmware requires one original symbol table"
        raise ValueError(message)
    table = tables[0]
    if (
        table[9] != SYMBOL.size
        or not table[5]
        or table[5] % SYMBOL.size
        or table[6] >= len(sections)
        or sections[table[6]][1] != STRING_TABLE
    ):
        message = "firmware original symbol table geometry or string link is invalid"
        raise ValueError(message)
    strings = sections[table[6]]
    names = content[strings[4] : strings[4] + strings[5]]
    result = {}
    for offset in range(table[4], table[4] + table[5], SYMBOL.size):
        name, info, _, section, address, size = SYMBOL.unpack_from(content, offset)
        if info >> 4 not in (GLOBAL_BINDING, WEAK_BINDING):
            continue
        end = names.find(b"\0", name)
        if name >= len(names) or end < 0:
            message = "firmware symbol name is outside the original string table"
            raise ValueError(message)
        try:
            identifier = names[name:end].decode("ascii")
        except UnicodeDecodeError as error:
            message = "firmware original symbol name is not ASCII"
            raise ValueError(message) from error
        if (
            not identifier
            or not section
            or (section != ABSOLUTE_SECTION and section >= len(sections))
        ):
            message = "firmware symbol is empty, undefined or has an invalid section"
            raise ValueError(message)
        if identifier in result:
            message = "firmware global symbol name is ambiguous"
            raise ValueError(message)
        result[identifier] = ElfSymbol(address, size, info & 15, section)
    return result
