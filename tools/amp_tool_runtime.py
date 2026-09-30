# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native tool ELF interpreter and loaded library identities

"""Read native Linux ELF interpreters and identify actual loader-resolved libraries."""

from __future__ import annotations

import struct
from pathlib import Path

from manifest_io import sha256_of_file

ELF_HEADER_SIZE = 64
PROGRAM_HEADER_SIZE = 56
PT_INTERP = 3


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
    if len(content) < ELF_HEADER_SIZE or content[:7] != b"\x7fELF\x02\x01\x01":
        message = "AMP native build tools require little-endian ELF64 executables"
        raise ValueError(message)
    offset = struct.unpack_from("<Q", content, 32)[0]
    size, count = struct.unpack_from("<HH", content, 54)
    if size != PROGRAM_HEADER_SIZE or offset + size * count > len(content):
        message = "AMP native tool has an invalid ELF program-header table"
        raise ValueError(message)
    for index in range(count):
        header = struct.unpack_from("<IIQQQQQQ", content, offset + size * index)
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


def library_identities(interpreter: Path, listing: str) -> dict[str, str]:
    """Hash actual filesystem libraries from the selected loader's successful list output.

    Parameters
    ----------
    interpreter
        Actual ELF interpreter selected by the executable.
    listing
        Complete successful bounded ``interpreter --list executable`` output.

    Returns
    -------
    dict of str to str
        Actual interpreter and resolved library file hashes; kernel vDSO excluded.

    Raises
    ------
    ValueError
        If any loader record does not identify an available absolute filesystem library.
    """
    identities = {str(interpreter): sha256_of_file(interpreter)}
    for line in listing.splitlines():
        value = line.strip()
        if value.startswith("linux-vdso.so.1 "):
            continue
        path = Path(value.split("=>", 1)[-1].strip().rsplit(" (", 1)[0])
        if not path.is_absolute() or not path.is_file():
            message = "AMP loader did not resolve an available absolute library: " + value
            raise ValueError(message)
        resolved = path.resolve()
        identities[str(resolved)] = sha256_of_file(resolved)
    return identities
