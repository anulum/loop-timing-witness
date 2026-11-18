# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native tool ELF interpreter and loaded library identities

"""Read native Linux ELF interpreters and identify actual loader-resolved libraries."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from manifest_io import sha256_of_file

ELF_HEADER_SIZE = 64
PROGRAM_HEADER_SIZE = 56
ET_EXEC = 2
PT_LOAD = 1
PT_INTERP = 3
PAGE_MASK = 0xFFF


def program_headers(content: bytes) -> list[tuple[int, ...]]:
    """Read the program-header records of a little-endian ELF64 file.

    Parameters
    ----------
    content
        Complete bytes of an actual selected native executable or library.

    Returns
    -------
    list of tuple of int
        Every record as type, flags, offset, virtual address, physical address, file size,
        memory size and alignment.

    Raises
    ------
    ValueError
        If the file is not little-endian ELF64 or its program-header table is invalid.
    """
    if len(content) < ELF_HEADER_SIZE or content[:7] != b"\x7fELF\x02\x01\x01":
        message = "AMP native build tools require little-endian ELF64 executables"
        raise ValueError(message)
    offset = struct.unpack_from("<Q", content, 32)[0]
    size, count = struct.unpack_from("<HH", content, 54)
    if size != PROGRAM_HEADER_SIZE or offset + size * count > len(content):
        message = "AMP native tool has an invalid ELF program-header table"
        raise ValueError(message)
    return [
        struct.unpack_from("<IIQQQQQQ", content, offset + size * index) for index in range(count)
    ]


def own_load_record(path: Path) -> re.Pattern[str]:
    """Return the pattern of the loader's list record of the listed executable itself.

    On the hosted ``ubuntu-26.04`` runner the glibc 2.43 loader begins ``--list`` output with
    a record for the listed executable: no name, only its load address. The riscv64
    assembler, a position-independent executable, was listed at 0x00007dbb3efad000, just
    below the vDSO and the loader, where the loader maps the program first. The same loader
    in an Ubuntu 26.04 container on another host prints no such record. The record names no
    library, and the caller hashes the executable's bytes itself.

    Parameters
    ----------
    path
        Actual selected native executable whose libraries the loader lists.

    Returns
    -------
    re.Pattern of str
        For a position-dependent (``ET_EXEC``) executable, ``(0x…)`` with the page of its
        lowest loadable segment, where it must load; otherwise any page-aligned address,
        which the kernel chooses.

    Raises
    ------
    ValueError
        If the file is not little-endian ELF64 or its program-header table is invalid.
    """
    content = path.read_bytes()
    headers = program_headers(content)
    loads = [header[3] for header in headers if header[0] == PT_LOAD]
    if struct.unpack_from("<H", content, 16)[0] != ET_EXEC or not loads:
        return re.compile(r"\(0x[0-9a-f]{13}000\)")
    return re.compile(re.escape(f"(0x{min(loads) & ~PAGE_MASK:016x})"))


def elf_interpreter(path: Path) -> Path:
    """Read the interpreter of an explicitly selected native Linux ELF64 executable.

    Parameters
    ----------
    path
        Actual selected native build executable, never a receipt-supplied command.

    Returns
    -------
    Path
        Original absolute ELF interpreter path resolved to its actual file.

    Raises
    ------
    ValueError
        If the executable is not little-endian ELF64 or lacks a valid dynamic interpreter.
    """
    content = path.read_bytes()
    for header in program_headers(content):
        if header[0] != PT_INTERP:
            continue
        start, length = header[2], header[5]
        value = content[start : start + length]
        if start + length > len(content) or not value.endswith(b"\0") or b"\0" in value[:-1]:
            message = "AMP native tool has an invalid ELF interpreter record"
            raise ValueError(message)
        interpreter = Path(value[:-1].decode("ascii"))
        if not interpreter.is_absolute() or not interpreter.is_file():
            message = "AMP native tool ELF interpreter is not an available absolute file"
            raise ValueError(message)
        return interpreter.resolve()
    message = "AMP native build tool lacks a dynamic ELF interpreter"
    raise ValueError(message)


def library_identities(
    interpreter: Path, listing: str, own_record: re.Pattern[str] | None = None
) -> dict[str, str]:
    """Hash actual filesystem libraries from the selected loader's successful list output.

    Parameters
    ----------
    interpreter
        Actual ELF interpreter selected by the executable.
    listing
        Complete successful bounded ``interpreter --list executable`` output.
    own_record
        Pattern of the listed executable's own nameless record from :func:`own_load_record`,
        admitted as the first record only, or ``None`` when the listing may carry none.

    Returns
    -------
    dict of str to str
        Actual interpreter and resolved library file hashes; kernel vDSO and the executable's
        own record excluded.

    Raises
    ------
    ValueError
        If any other loader record does not identify an available absolute filesystem library.
    """
    identities = {str(interpreter): sha256_of_file(interpreter)}
    records = [line.strip() for line in listing.splitlines()]
    own = bool(records) and own_record is not None and own_record.fullmatch(records[0]) is not None
    for value in records[int(own) :]:
        if value.startswith("linux-vdso.so.1 "):
            continue
        path = Path(value.split("=>", 1)[-1].strip().rsplit(" (", 1)[0])
        if not path.is_absolute() or not path.is_file():
            message = (
                f"AMP loader did not resolve an available absolute library: {value}; "
                f"complete listing: {' | '.join(records)}"
            )
            raise ValueError(message)
        resolved = path.resolve()
        identities[str(resolved)] = sha256_of_file(resolved)
    return identities
