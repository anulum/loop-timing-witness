# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — firmware ELF reading corpus shared with the native analysis

"""Hold the Python firmware ELF readers' outcomes on real and changed images in a shared corpus.

Two real images are committed inside the corpus, as hexadecimal bytes: the
small image the load tests link from one assembly file, and a whole firmware
compiled from the repository's startup, controller, exit and contract sources.
Both were built once by the pinned RV64 cross compiler; ``BUILDS`` records
how. They are kept as bytes rather than rebuilt here, because the linker that
the compiler package pulls in is not pinned and a rebuilt image could differ
by a byte. The test takes the images from the committed corpus, requires
their recorded digests and rebuilds everything else from them.

For each image the corpus records what ``admit_elf`` returns for the
firmware reservation and what ``read_symbols`` returns, or the text each
refuses with. Named cases change several fields together, cut the image or
change the reservation. The sweep changes one field at a time: every field of
the ELF header and of each program header, section header and symbol, across
the values around each refusal bound (``_symbol_rows`` says which symbol
fields). A sweep row stores ``null`` where an outcome equals the image's own.
The native analysis reads the same corpus in its unit tests.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Final

from loop_timing_witness.amp_elf import (
    LOAD_TYPE,
    MAX_IMAGE_BYTES,
    READ_EXECUTE,
    READ_WRITE,
    admit_elf,
)
from loop_timing_witness.amp_elf_symbols import (
    GLOBAL_BINDING,
    SYMBOL_TABLE,
    WEAK_BINDING,
    read_symbols,
)
from loop_timing_witness.device_tree_resources import Region

DATA: Final = Path(__file__).resolve().parents[1] / "analysis/rust/tests/data"
CORPUS: Final = DATA / "amp-elf-cases.json"
DIGESTS: Final = {
    "linked": "fea4cad6edffab98fc8ad20ac66ca1fb82d7e84c55a2def88884bd2fe1dabb68",
    "firmware": "8f09daaa5a5e096de056e45c4a70fb0c98bb7874c24729cfd0c1323f8a8dcf20",
}
RAM: Final = Region(0x80000000, 0x80000)
LINK: Final = (
    "-nostdlib -nostartfiles -static -no-pie -march=rv64imac_zicsr_zifencei -mabi=lp64 "
    "-mcmodel=medany -Wl,--build-id=none -Wl,--defsym=__witness_ram_origin=0x80000000 "
    "-Wl,--defsym=__witness_ram_length=0x80000 -Wl,--defsym=__witness_stack_size=16384 "
    "-T runtime/bare_metal/firmware.ld"
)
BUILDS: Final = {
    "compiler": "riscv64-linux-gnu-gcc-13 (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0",
    "linker": "GNU ld (GNU Binutils for Ubuntu) 2.42",
    "linked": {
        "source": (
            'entry.S: .section .text.start,"ax" / .global _start / _start: wfi / j _start / '
            '.section .data,"aw" / .word 7'
        ),
        "command": f"{LINK} entry.S",
    },
    "firmware": {
        "source": (
            "contract.c rendered by render_contract from the platform of "
            "tests/test_amp_platform.py and the run of tests/test_amp_contract.py, "
            "SHA-256 71942362e52e821e3774889493b5656c0c541f046c684391ca9c17dce1ad9aca"
        ),
        "command": (
            "-std=gnu11 -O2 -ffreestanding -fno-builtin -fno-pie -Wall -Wextra -Werror "
            f"-Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes -I. {LINK} "
            "runtime/bare_metal/entry.S runtime/bare_metal/amp_controller.c "
            "runtime/isa/amp_exit.c controllers/c/witness_controller.c contract.c"
        ),
        "inputs": {
            "runtime/bare_metal/firmware.ld": (
                "9c0199f4d1b808fdcbcbf3b8d9c771c6d409c3be76a82c664022917a7c1ff694"
            ),
            "runtime/bare_metal/entry.S": (
                "fb3b9297bdd1e264d2bba09556061d3b8680a288ed498b8de27c6ed6c490ac12"
            ),
            "runtime/bare_metal/amp_controller.c": (
                "e585bc70242cdac634c1d17d6494d89bb42a27e8645770adea7bffb98adab85c"
            ),
            "runtime/isa/amp_exit.c": (
                "0261401cbf235ec6907fc395811c98f734781e8f9617bd85bb8ea8eb1263bb81"
            ),
            "controllers/c/witness_controller.c": (
                "bf7f0e5029f81ed0da6b6b9eab787412f2be922fb85ac6dd24f70cb2cd474b63"
            ),
        },
    },
}
HEADER: Final = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM: Final = struct.Struct("<IIQQQQQQ")
SECTION: Final = struct.Struct("<IIQQQQIIQQ")
SYMBOL: Final = struct.Struct("<IBBHQQ")
# Field name, offset within its record, width in bytes.
HEADER_FIELDS: Final = (
    ("type", 16, 2),
    ("machine", 18, 2),
    ("version", 20, 4),
    ("entry", 24, 8),
    ("program table", 32, 8),
    ("section table", 40, 8),
    ("flags", 48, 4),
    ("header size", 52, 2),
    ("program entry size", 54, 2),
    ("program count", 56, 2),
    ("section entry size", 58, 2),
    ("section count", 60, 2),
    ("section names", 62, 2),
)
PROGRAM_FIELDS: Final = (
    ("type", 0, 4),
    ("flags", 4, 4),
    ("offset", 8, 8),
    ("virtual", 16, 8),
    ("physical", 24, 8),
    ("file size", 32, 8),
    ("memory size", 40, 8),
    ("alignment", 48, 8),
)
SECTION_FIELDS: Final = (
    ("name", 0, 4),
    ("type", 4, 4),
    ("flags", 8, 8),
    ("address", 16, 8),
    ("offset", 24, 8),
    ("size", 32, 8),
    ("link", 40, 4),
    ("info", 44, 4),
    ("alignment", 48, 8),
    ("entry size", 56, 8),
)
SYMBOL_FIELDS: Final = (
    ("name", 0, 4),
    ("info", 4, 1),
    ("other", 5, 1),
    ("section", 6, 2),
    ("value", 8, 8),
    ("size", 16, 8),
)


def _admission(content: bytes, reservation: Region) -> dict[str, Any]:
    """Return the load segments ``admit_elf`` admits, or its refusal.

    Parameters
    ----------
    content
        Whole image.
    reservation
        Firmware reservation.

    Returns
    -------
    dict[str, Any]
        ``{"segments": [[offset, address, file, memory, flags], ...]}`` or ``{"refusal": text}``.
    """
    try:
        segments = admit_elf(content, reservation)
    except ValueError as error:
        return {"refusal": str(error)}
    return {
        "segments": [
            [item.offset, item.address, item.file_bytes, item.memory_bytes, item.flags]
            for item in segments
        ]
    }


def _symbols(content: bytes, *, whole: bool) -> dict[str, Any]:
    """Return the symbols ``read_symbols`` reads, or their digest, or its refusal.

    The digest is the SHA-256 of each symbol in table order: its name's
    length as a little-endian 32-bit word, the ASCII name, the value and
    size as 64-bit words, the type as a byte and the section as a 16-bit
    word.

    Parameters
    ----------
    content
        Whole image.
    whole
        Whether to record every symbol instead of the digest.

    Returns
    -------
    dict[str, Any]
        ``{"symbols": {...}}``, ``{"symbols_sha256": hex}`` or ``{"refusal": text}``.
    """
    try:
        symbols = read_symbols(content)
    except ValueError as error:
        return {"refusal": str(error)}
    if whole:
        return {
            "symbols": {
                name: [item.address, item.size, item.kind, item.section]
                for name, item in symbols.items()
            }
        }
    digest = hashlib.sha256()
    for name, item in symbols.items():
        raw = name.encode("ascii")
        digest.update(struct.pack("<I", len(raw)) + raw)
        digest.update(struct.pack("<QQBH", item.address, item.size, item.kind, item.section))
    return {"symbols_sha256": digest.hexdigest()}


def _tables(content: bytes) -> tuple[list[int], list[tuple[int, ...]], list[int], int, bytes]:
    """Return an image's program headers, section headers, symbols and symbol names.

    Parameters
    ----------
    content
        Whole original image.

    Returns
    -------
    tuple
        Program header offsets, section headers, symbol record offsets, and the
        offset and bytes of the symbol names.
    """
    header = HEADER.unpack_from(content)
    programs = [header[5] + index * PROGRAM.size for index in range(header[10])]
    sections = [
        SECTION.unpack_from(content, header[6] + index * SECTION.size)
        for index in range(header[12])
    ]
    table = next(section for section in sections if section[1] == SYMBOL_TABLE)
    strings = sections[table[6]]
    symbols = list(range(table[4], table[4] + table[5], SYMBOL.size))
    return programs, sections, symbols, strings[4], content[strings[4] : strings[4] + strings[5]]


def _load(content: bytes, flags: int) -> tuple[int, ...]:
    """Return the image's load program header with the given permissions.

    Parameters
    ----------
    content
        Whole original image.
    flags
        Exact permission bits.

    Returns
    -------
    tuple[int, ...]
        Program header fields.
    """
    programs = _tables(content)[0]
    loads = [PROGRAM.unpack_from(content, offset) for offset in programs]
    return next(load for load in loads if load[0] == LOAD_TYPE and load[1] == flags)


def _values(width: int, original: int, extras: set[int]) -> list[int]:
    """Return the replacement values of one field around its refusal bounds.

    Parameters
    ----------
    width
        Field width in bytes.
    original
        The field's value in the image.
    extras
        Field-specific bounds.

    Returns
    -------
    list[int]
        Sorted values that fit the field and differ from the original.
    """
    top = (1 << (8 * width)) - 1
    found = {0, 1, original - 1, original + 1, top, *extras}
    return sorted(value for value in found if 0 <= value <= top and value != original)


def _rows(index: int, start: int, width: int, values: list[int]) -> list[list[Any]]:
    """Return sweep rows that write each value into one little-endian field.

    Parameters
    ----------
    index
        Image index in the corpus.
    start
        Field offset in the image.
    width
        Field width in bytes.
    values
        Replacement values.

    Returns
    -------
    list[list[Any]]
        ``[image, offset, hex]`` rows, without outcomes yet.
    """
    return [[index, start, value.to_bytes(width, "little").hex()] for value in values]


def _header_rows(index: int, content: bytes) -> list[list[Any]]:
    """Return sweep rows over the identity bytes and every ELF header field.

    Parameters
    ----------
    index
        Image index in the corpus.
    content
        Whole original image.

    Returns
    -------
    list[list[Any]]
        Rows without outcomes.
    """
    length = len(content)
    header = HEADER.unpack_from(content)
    sections = _tables(content)[1]
    executable = _load(content, READ_EXECUTE)
    rows = [[index, offset, f"{content[offset] ^ 0x01:02x}"] for offset in range(16)]
    rows += [[index, offset, "ff"] for offset in range(16)]
    extras: dict[str, set[int]] = {
        "type": {1, 3, 4},
        "machine": {62, 242, 244},
        "version": {2},
        "entry": {executable[4] + executable[5], executable[4] + executable[5] - 1},
        "program table": {
            63,
            64,
            length - header[10] * PROGRAM.size,
            length - header[10] * PROGRAM.size + 1,
        },
        "section table": {
            63,
            64,
            length - header[12] * SECTION.size,
            length - header[12] * SECTION.size + 1,
        },
        "flags": {2, 3, 4, 5, 8},
        "header size": {63, 65},
        "program entry size": {55, 57},
        "program count": {128, 129},
        "section entry size": {63, 65},
        "section count": {len(sections) - 1, 16384, 16385},
        "section names": set(),
    }
    for name, offset, width in HEADER_FIELDS:
        original = int.from_bytes(content[offset : offset + width], "little")
        rows += _rows(index, offset, width, _values(width, original, extras[name]))
    return rows


def _program_rows(index: int, content: bytes) -> list[list[Any]]:
    """Return sweep rows over every field of every program header.

    The virtual and physical addresses are also changed together, since a
    load segment whose two addresses differ is refused before its extent.

    Parameters
    ----------
    index
        Image index in the corpus.
    content
        Whole original image.

    Returns
    -------
    list[list[Any]]
        Rows without outcomes.
    """
    length, end = len(content), RAM.address + RAM.size
    programs = _tables(content)[0]
    records = [PROGRAM.unpack_from(content, offset) for offset in programs]
    offsets = {record[2] for record in records}
    addresses = {record[4] for record in records}
    rows: list[list[Any]] = []
    for start, record in zip(programs, records, strict=True):
        offset, physical, file_bytes, memory_bytes, alignment = (record[2], *record[4:])
        extras: dict[str, set[int]] = {
            "type": {2, 3, 4, 6, 0x6474E551, 0x70000003},
            "flags": {4, 5, 6, 7},
            "offset": {
                *offsets,
                length - file_bytes,
                length - file_bytes + 1,
                offset + alignment,
                1 << 63,
            },
            "virtual": {physical},
            "physical": set(),
            "file size": {memory_bytes, memory_bytes + 1, length - offset, length - offset + 1},
            "memory size": {
                file_bytes,
                file_bytes - 1,
                end - physical,
                end - physical + 1,
                *(other[4] - physical for other in records if other[4] > physical),
            },
            "alignment": {2, 3, 4095, 4096, 4097, 8192, 3 * 4096, 1 << 63},
        }
        for name, place, width in PROGRAM_FIELDS:
            original = int.from_bytes(content[start + place : start + place + width], "little")
            rows += _rows(index, start + place, width, _values(width, original, extras[name]))
        both = {
            *addresses,
            RAM.address - 1,
            RAM.address + 1,
            RAM.address + RAM.size // 2,
            end - memory_bytes,
            end - memory_bytes + 1,
            (1 << 64) - memory_bytes,
            (1 << 64) - memory_bytes + 1,
        }
        for value in sorted(both - {physical}):
            if 0 <= value < 1 << 64:
                rows.append([index, start + 16, (value.to_bytes(8, "little") * 2).hex()])
    return rows


def _section_rows(index: int, content: bytes) -> list[list[Any]]:
    """Return sweep rows over every field of every section header.

    Parameters
    ----------
    index
        Image index in the corpus.
    content
        Whole original image.

    Returns
    -------
    list[list[Any]]
        Rows without outcomes.
    """
    length = len(content)
    header = HEADER.unpack_from(content)
    sections = _tables(content)[1]
    count = len(sections)
    rows: list[list[Any]] = []
    for position, section in enumerate(sections):
        start = header[6] + position * SECTION.size
        offset, size = section[4], section[5]
        extras: dict[str, set[int]] = {
            "name": set(),
            "type": {0, 1, 2, 3, 8, 11},
            "flags": set(),
            "address": set(),
            "offset": {length - size, length - size + 1, 1 << 63},
            "size": {23, 24, 25, length - offset, length - offset + 1, size - 24, size + 24},
            "link": {
                count - 1,
                count,
                *(other for other in range(count) if sections[other][1] == 1),
            },
            "info": set(),
            "alignment": set(),
            "entry size": {23, 24, 25},
        }
        for name, place, width in SECTION_FIELDS:
            original = int.from_bytes(content[start + place : start + place + width], "little")
            values = _values(width, original, extras[name])
            if not extras[name] and name != "link":
                values = values[:1]
            rows += _rows(index, start + place, width, values)
    return rows


def _symbol_rows(index: int, content: bytes) -> list[list[Any]]:
    """Return sweep rows over the symbol records.

    The reader skips local symbols, so each local symbol gets only binding
    changes, which decide whether it is read at all. Each global or weak
    symbol gets every field: its name offset at the table's last byte, past
    the table, and at the first global's name; its section around the table
    count and the reserved indexes; its binding and type. The value, size and
    other byte are only copied or ignored, so the first global alone gets them.

    Parameters
    ----------
    index
        Image index in the corpus.
    content
        Whole original image.

    Returns
    -------
    list[list[Any]]
        Rows without outcomes.
    """
    _, sections, symbols, _, names = _tables(content)
    count = len(sections)
    globals_ = [
        offset
        for offset in symbols
        if SYMBOL.unpack_from(content, offset)[1] >> 4 in (GLOBAL_BINDING, WEAK_BINDING)
    ]
    shared = SYMBOL.unpack_from(content, globals_[0])[0]
    rows: list[list[Any]] = []
    for start in symbols:
        extras: dict[str, set[int]] = {
            "name": {len(names) - 1, len(names), shared},
            "info": {0x00, 0x10, 0x11, 0x12, 0x20, 0x22, 0x30, 0xF0},
            "other": set(),
            "section": {count - 1, count, 0xFFF0, 0xFFF1, 0xFFF2},
            "value": set(),
            "size": set(),
        }
        for name, place, width in SYMBOL_FIELDS:
            if start not in globals_ and name != "info":
                continue
            if start != globals_[0] and name in ("other", "value", "size"):
                continue
            original = int.from_bytes(content[start + place : start + place + width], "little")
            values = _values(width, original, extras[name])
            if name in ("other", "value", "size"):
                values = [value for value in values if value in (0, (1 << (8 * width)) - 1)]
            rows += _rows(index, start + place, width, values)
    return rows


def _named(images: dict[str, bytes]) -> list[dict[str, Any]]:
    """Return named changes of several fields, cut or padded images and other reservations.

    Parameters
    ----------
    images
        Original images by name.

    Returns
    -------
    list[dict[str, Any]]
        Cases with their edits, length or reservation, without outcomes yet.
    """
    cases: list[dict[str, Any]] = []
    for name, content in images.items():
        header = HEADER.unpack_from(content)
        _, _, symbols, table, names = _tables(content)
        table_end = header[5] + header[10] * PROGRAM.size
        cases.extend(
            {"name": f"{name} cut to {length}", "image": name, "length": length}
            for length in (0, 63, 64, table_end - 1, table_end, len(content) - 1)
        )
        cases.extend(
            {"name": f"{name} padded to {length}", "image": name, "pad": length}
            for length in (MAX_IMAGE_BYTES, MAX_IMAGE_BYTES + 1)
        )
        writable = _load(content, READ_WRITE)
        end = writable[4] + writable[6]
        cases += _placements(name, content)
        for label, reservation in {
            "exact reservation": (RAM.address, end - RAM.address),
            "reservation one byte short": (RAM.address, end - RAM.address - 1),
            "reservation after the entry": (RAM.address + 4096, RAM.size),
            "reservation at the top": ((1 << 64) - RAM.size, RAM.size),
        }.items():
            cases.append(
                {"name": f"{name} {label}", "image": name, "reservation": list(reservation)}
            )
        globals_ = [
            offset
            for offset in symbols
            if SYMBOL.unpack_from(content, offset)[1] >> 4 in (GLOBAL_BINDING, WEAK_BINDING)
        ]
        first = SYMBOL.unpack_from(content, globals_[0])[0]
        cases.append(
            {
                "name": f"{name} global name not ASCII",
                "image": name,
                "edits": [[table + first, "80"]],
            }
        )
        cases.append(
            {
                "name": f"{name} global name runs past its table",
                "image": name,
                "edits": [
                    [table + len(names) - 1, "41"],
                    [globals_[0], struct.pack("<I", len(names) - 1).hex()],
                ],
            }
        )
    return cases


def _placements(name: str, content: bytes) -> list[dict[str, Any]]:
    """Return load segments moved to meet each other or the end of the address space.

    Two segments that meet in memory or in the file do not overlap, in
    either order. A reservation at the top of the address space, with the
    entry and both segments moved into it, admits a segment that ends exactly
    at the end of the address space and refuses one a byte longer.

    Parameters
    ----------
    name
        Image name.
    content
        Whole original image.

    Returns
    -------
    list[dict[str, Any]]
        Cases with their edits and reservation, without outcomes yet.
    """
    programs = _tables(content)[0]
    starts = {PROGRAM.unpack_from(content, offset)[1]: offset for offset in programs}
    executable, writable = _load(content, READ_EXECUTE), _load(content, READ_WRITE)
    first, second = starts[READ_EXECUTE], starts[READ_WRITE]
    middle = RAM.address + RAM.size // 2
    top = (1 << 64) - RAM.size
    gap = writable[4] - executable[4]

    def word(value: int) -> str:
        return value.to_bytes(8, "little").hex()

    at_top = [[24, word(top)], [first + 16, word(top) * 2], [second + 16, word(top + gap) * 2]]
    reservation = [top, RAM.size]
    return [
        {
            "name": f"{name} later segment ends where the earlier begins",
            "image": name,
            "edits": [[first + 16, word(middle) * 2], [second + 40, word(middle - writable[4])]],
        },
        {
            "name": f"{name} load segments meet in memory and in the file",
            "image": name,
            "edits": [
                [first + 32, word(writable[2] - executable[2])],
                [first + 40, word(writable[2] - executable[2])],
            ],
        },
        {
            "name": f"{name} later segment's file ends where the earlier's begins",
            "image": name,
            "edits": [[second + 8, word(0)], [second + 32, word(executable[2])]],
        },
        {
            "name": f"{name} at the top of the address space",
            "image": name,
            "edits": at_top,
            "reservation": reservation,
        },
        {
            "name": f"{name} segment ends at the end of the address space",
            "image": name,
            "edits": [*at_top, [second + 40, word((1 << 64) - top - gap)]],
            "reservation": reservation,
        },
        {
            "name": f"{name} segment passes the end of the address space",
            "image": name,
            "edits": [*at_top, [second + 40, word((1 << 64) - top - gap + 1)]],
            "reservation": reservation,
        },
    ]


def _apply(content: bytes, edits: list[list[Any]]) -> bytes:
    """Apply ``[offset, hex]`` edits to a copy of an image.

    Parameters
    ----------
    content
        Original image.
    edits
        Byte replacements.

    Returns
    -------
    bytes
        Changed copy.
    """
    changed = bytearray(content)
    for offset, text in edits:
        data = bytes.fromhex(text)
        changed[offset : offset + len(data)] = data
    return bytes(changed)


def _refusals(value: object) -> set[str]:
    """Return every refusal text held in a corpus value.

    Parameters
    ----------
    value
        Corpus value.

    Returns
    -------
    set[str]
        Refusal texts.
    """
    if isinstance(value, dict):
        found = {value["refusal"]} if isinstance(value.get("refusal"), str) else set()
        return found.union(*(_refusals(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_refusals(item) for item in value))
    return set()


def _indexed(value: object, texts: dict[str, int]) -> object:
    """Replace every refusal text by its index in the sorted text table.

    Parameters
    ----------
    value
        Corpus value.
    texts
        Index by refusal text.

    Returns
    -------
    object
        Value with integer refusals.
    """
    if isinstance(value, dict):
        return {
            key: texts[item] if key == "refusal" else _indexed(item, texts)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_indexed(item, texts) for item in value]
    return value


def corpus(images: dict[str, bytes]) -> dict[str, Any]:
    """Build the complete corpus from the two images and Python's readers.

    Parameters
    ----------
    images
        The linked and firmware images, by name; they are taken in the order of ``DIGESTS``.

    Returns
    -------
    dict[str, Any]
        Images with their provenance, base outcomes, named cases and the sweep.
    """
    images = {name: images[name] for name in DIGESTS}
    bases = {
        name: {"admit": _admission(content, RAM), "symbols": _symbols(content, whole=True)}
        for name, content in images.items()
    }
    cases = []
    for case in _named(images):
        content = images[case["image"]]
        content = _apply(content, case.get("edits", []))[: case.get("length", len(content))]
        content += bytes(case.get("pad", len(content)) - len(content))
        reservation = Region(*case.get("reservation", (RAM.address, RAM.size)))
        whole = _admission(content, reservation), _symbols(content, whole=False)
        cases.append({**case, "admit": whole[0], "symbols": whole[1]})
    sweep: list[list[Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for index, content in enumerate(images.values()):
        own = _admission(content, RAM), _symbols(content, whole=False)
        rows = [
            *_header_rows(index, content),
            *_program_rows(index, content),
            *_section_rows(index, content),
            *_symbol_rows(index, content),
        ]
        for row in rows:
            key = (row[0], row[1], row[2])
            if key in seen:
                continue
            seen.add(key)
            changed = _apply(content, [row[1:]])
            admitted, symbols = _admission(changed, RAM), _symbols(changed, whole=False)
            sweep.append(
                [
                    *row,
                    None if admitted == own[0] else admitted,
                    None if symbols == own[1] else symbols,
                ]
            )
    texts = sorted(_refusals([bases, cases, sweep]))
    numbers = {text: number for number, text in enumerate(texts)}
    return {
        "schema": "loop-timing-witness.amp-elf-cases.v1",
        "description": (
            "Python firmware ELF readers' outcomes. images holds each real image as hexadecimal "
            "bytes, with its SHA-256 and how it was built; the sweep numbers them linked 0, "
            "firmware 1. admit is admit_elf's outcome for the reservation [address, size] (by "
            "default the firmware RAM), symbols is read_symbols' outcome; a "
            "refusal is an index into texts. symbols_sha256 hashes each symbol in table order: "
            "its name's length as a little-endian 32-bit word, the ASCII name, value and size as "
            "64-bit words, type as a byte and section as a 16-bit word. A named case changes an "
            "image by [offset, hex] edits, cuts it to length, pads it with zeros to pad bytes or "
            "changes the reservation. Each "
            "sweep row is [image index, offset, hex, admit, symbols], with null where an outcome "
            "equals the unchanged image's."
        ),
        "reservation": [RAM.address, RAM.size],
        "images": {
            name: {
                "hex": content.hex(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "build": BUILDS[name],
            }
            for name, content in images.items()
        },
        "toolchain": {"compiler": BUILDS["compiler"], "linker": BUILDS["linker"]},
        "texts": texts,
        "bases": _indexed(bases, numbers),
        "cases": _indexed(cases, numbers),
        "sweep": _indexed(sweep, numbers),
    }


def _text(document: dict[str, Any]) -> str:
    """Return the committed text form of the corpus.

    Parameters
    ----------
    document
        Corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_outcomes() -> None:
    """Rebuild the corpus from its committed images and require the committed file."""
    committed = CORPUS.read_text(encoding="utf-8")
    images = {
        name: bytes.fromhex(entry["hex"]) for name, entry in json.loads(committed)["images"].items()
    }
    assert {name: hashlib.sha256(image).hexdigest() for name, image in images.items()} == DIGESTS
    assert committed == _text(corpus(images))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
