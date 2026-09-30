# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real RV64 linked image load admission and malformed image refusals

"""Exercise ELF admission using actual cross-compiled firmware and explicit corruptions."""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
from typing import TYPE_CHECKING

import pytest
from amp_elf import admit_elf
from device_tree_resources import Region

if TYPE_CHECKING:
    from pathlib import Path

HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM = struct.Struct("<IIQQQQQQ")
RAM = Region(0x80000000, 0x80000)


@pytest.fixture
def linked_image(tmp_path: Path) -> bytes:
    """Cross-compile and link a real freestanding image with the production linker script.

    Parameters
    ----------
    tmp_path
        Exact owned assembly and ELF staging directory.

    Returns
    -------
    bytes
        Original RV64 linker-produced complete executable.
    """
    compiler = os.environ.get("WITNESS_RV64_CC") or shutil.which("riscv64-linux-gnu-gcc")
    assert compiler is not None, "actual RV64 compiler is required"
    source = tmp_path / "entry.S"
    source.write_text(
        '.section .text.start,"ax"\n.global _start\n_start: wfi\nj _start\n'
        '.section .data,"aw"\n.word 7\n',
        encoding="ascii",
    )
    image = tmp_path / "firmware.elf"
    subprocess.run(
        [
            compiler,
            "-nostdlib",
            "-nostartfiles",
            "-static",
            "-no-pie",
            "-march=rv64imac_zicsr_zifencei",
            "-mabi=lp64",
            "-mcmodel=medany",
            "-Wl,--build-id=none",
            "-Wl,--defsym=__witness_ram_origin=0x80000000",
            "-Wl,--defsym=__witness_ram_length=0x80000",
            "-Wl,--defsym=__witness_stack_size=16384",
            "-T",
            "runtime/bare_metal/firmware.ld",
            str(source),
            "-o",
            str(image),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return image.read_bytes()


def test_original_linked_load_extents(linked_image: bytes) -> None:
    """Admit actual RX/RW segments and zero-filled reserved stack memory.

    Parameters
    ----------
    linked_image
        Original cross-linked image.
    """
    segments = admit_elf(linked_image, RAM)
    assert [segment.flags for segment in segments] == [5, 6]
    assert segments[0].address == RAM.address
    assert segments[1].memory_bytes > segments[1].file_bytes


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        (0, b"bad" + bytes(13), "soft-float RV64"),
        (1, 3, "soft-float RV64"),
        (2, 62, "soft-float RV64"),
        (3, 2, "soft-float RV64"),
        (4, 0x80000004, "entry differs"),
        (5, 0, "header geometry"),
        (5, 0xFFFFFFFFFFFFFFFF, "header geometry"),
        (7, 4, "soft-float RV64"),
        (8, 63, "header geometry"),
        (9, 55, "header geometry"),
        (10, 0, "header geometry"),
        (10, 129, "header geometry"),
    ],
)
def test_corrupted_original_header(
    linked_image: bytes, field: int, value: int | bytes, finding: str
) -> None:
    """Refuse explicit corruptions of an originally linked executable header.

    Parameters
    ----------
    linked_image
        Original real compiler output.
    field
        Header field index to corrupt.
    value
        Invalid original-field replacement.
    finding
        Required admission refusal.
    """
    values = list(HEADER.unpack_from(linked_image))
    values[field] = value
    altered = bytearray(linked_image)
    HEADER.pack_into(altered, 0, *values)
    with pytest.raises(ValueError, match=finding):
        admit_elf(bytes(altered), RAM)


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        (0, 2, "dynamic loader"),
        (0, 3, "dynamic loader"),
        (0, 0, "entry lacks"),
        (1, 7, "permissions"),
        (1, 6, "entry lacks"),
        (2, 0xFFFFFFFFFFFFFFFF, "file extent is truncated"),
        (3, 0x80000001, "geometry"),
        (5, 1000000, "file extent is truncated"),
        (6, 0, "permissions"),
        (6, 1, "permissions"),
        (6, 0x100000, "reserved RAM"),
        (7, 0, "geometry"),
        (7, 4097, "geometry"),
    ],
)
def test_corrupted_original_segment(
    linked_image: bytes, field: int, value: int, finding: str
) -> None:
    """Refuse corrupt load semantics and permissions using actual image bytes.

    Parameters
    ----------
    linked_image
        Original real compiler output.
    field
        First load header field index.
    value
        Invalid field replacement.
    finding
        Required admission refusal.
    """
    header = HEADER.unpack_from(linked_image)
    offset = int(header[5])
    while PROGRAM.unpack_from(linked_image, offset)[0] != 1:
        offset += PROGRAM.size
    values = list(PROGRAM.unpack_from(linked_image, offset))
    values[field] = value
    altered = bytearray(linked_image)
    PROGRAM.pack_into(altered, offset, *values)
    with pytest.raises(ValueError, match=finding):
        admit_elf(bytes(altered), RAM)


@pytest.mark.parametrize("collision", ["file", "memory"])
def test_original_segment_aliases(linked_image: bytes, collision: str) -> None:
    """Refuse overlapping memory or initialized file extents in real linked images.

    Parameters
    ----------
    linked_image
        Actual linked image.
    collision
        Original extent to corrupt into an alias.
    """
    header = HEADER.unpack_from(linked_image)
    offsets = [
        int(header[5]) + i * PROGRAM.size
        for i in range(int(header[10]))
        if PROGRAM.unpack_from(linked_image, int(header[5]) + i * PROGRAM.size)[0] == 1
    ]
    first = PROGRAM.unpack_from(linked_image, offsets[0])
    values = list(PROGRAM.unpack_from(linked_image, offsets[1]))
    if collision == "file":
        values[2] = first[2]
    else:
        values[3] = first[3]
        values[4] = first[4]
    altered = bytearray(linked_image)
    PROGRAM.pack_into(altered, offsets[1], *values)
    with pytest.raises(ValueError, match="load segments overlap"):
        admit_elf(bytes(altered), RAM)


def test_truncated_original_image(linked_image: bytes) -> None:
    """Refuse missing executable identity bytes without interpreting a partial header.

    Parameters
    ----------
    linked_image
        Actual linked image.
    """
    with pytest.raises(ValueError, match="image size"):
        admit_elf(linked_image[:63], RAM)
