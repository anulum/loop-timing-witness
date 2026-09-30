# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real DTB compilation and malformed resource refusal

"""Exercise the public binary decoder using actual dtc output and corruptions."""

from __future__ import annotations

import shutil
import struct
import subprocess
from typing import TYPE_CHECKING

import pytest
from device_tree_blob import decode_device_tree

if TYPE_CHECKING:
    from pathlib import Path

HEADER = struct.Struct(">10I")
WORD = struct.Struct(">I")
SOURCE = """/dts-v1/;
/memreserve/ 0x80010000 0x10000;
/ {
    #address-cells = <2>;
    #size-cells = <2>;
    compatible = "anulum,witness-platform-test";
    cpus {
        #address-cells = <1>;
        #size-cells = <0>;
        cpu@1 { device_type = "cpu"; reg = <1>; };
    };
    memory@80000000 { device_type = "memory"; reg = <0 0x80000000 0 0x100000>; };
};
"""


@pytest.fixture
def compiled_tree(tmp_path: Path) -> bytes:
    """Compile a real topology and reservation map through the native dtc entry point.

    Parameters
    ----------
    tmp_path
        Exact pytest-owned directory for source and compiled bytes.

    Returns
    -------
    bytes
        Original successful compiler output.
    """
    compiler = shutil.which("dtc")
    assert compiler is not None, "dtc is required for actual binary device-tree tests"
    source = tmp_path / "platform.dts"
    output = tmp_path / "platform.dtb"
    source.write_text(SOURCE, encoding="ascii")
    subprocess.run(
        [compiler, "-I", "dts", "-O", "dtb", "-o", str(output), str(source)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    return output.read_bytes()


def test_actual_compiler_topology_and_reservations(compiled_tree: bytes) -> None:
    """Retain CPU identifiers, device bytes and the original reserved physical extent.

    Parameters
    ----------
    compiled_tree
        Actual dtc-produced platform bytes.
    """
    tree = decode_device_tree(compiled_tree)
    assert tree.reservations == ((0x80010000, 0x10000),)
    assert set(tree.nodes) == {"/", "/cpus", "/cpus/cpu@1", "/memory@80000000"}
    assert tree.nodes["/cpus/cpu@1"].properties["reg"] == WORD.pack(1)
    assert tree.nodes["/"].properties["compatible"] == b"anulum,witness-platform-test\0"


@pytest.mark.parametrize(
    ("index", "value", "finding"),
    [
        (0, 0, "magic"),
        (1, 40, "total size"),
        (2, 41, "alignment"),
        (3, 0, "bounds"),
        (4, 41, "alignment"),
        (5, 16, "version"),
        (6, 18, "version"),
        (8, 0xFFFFFFFF, "bounds"),
        (9, 0, "bounds"),
        (9, 3, "alignment"),
    ],
)
def test_corrupt_header_refused(compiled_tree: bytes, index: int, value: int, finding: str) -> None:
    """Refuse a real compiled file with one invalid block or version field.

    Parameters
    ----------
    compiled_tree
        Original successful compiler bytes.
    index
        Header field to corrupt.
    value
        Invalid replacement value.
    finding
        Required refusal diagnostic.
    """
    raw = bytearray(compiled_tree)
    WORD.pack_into(raw, index * WORD.size, value)
    with pytest.raises(ValueError, match=finding):
        decode_device_tree(bytes(raw))


@pytest.mark.parametrize("content", [b"", b"\0" * 39, b"\0" * (16 * 1024 * 1024 + 1)])
def test_blob_size_refused(content: bytes) -> None:
    """Reject truncated headers and excessive files before decoding their offsets.

    Parameters
    ----------
    content
        File bytes outside the declared parser bounds.
    """
    with pytest.raises(ValueError, match="size outside"):
        decode_device_tree(content)


@pytest.mark.parametrize(
    "variant",
    [
        "block_overlap",
        "reservation_overlap",
        "reservation_zero",
        "reservation_overflow",
        "reservation_terminator",
    ],
)
def test_invalid_reservation_layout_refused(compiled_tree: bytes, variant: str) -> None:
    """Refuse corrupted actual reservation maps and overlapping file blocks.

    Parameters
    ----------
    compiled_tree
        Original dtc output with one reservation and its terminator.
    variant
        Physical or binary extent corruption to apply.
    """
    raw = bytearray(compiled_tree)
    header = list(HEADER.unpack_from(raw))
    reserved = header[4]
    if variant == "block_overlap":
        WORD.pack_into(raw, 3 * WORD.size, header[2])
    elif variant == "reservation_zero":
        struct.pack_into(">QQ", raw, reserved, 1, 0)
    elif variant == "reservation_overflow":
        struct.pack_into(">QQ", raw, reserved, (1 << 64) - 1, 2)
    elif variant == "reservation_terminator":
        struct.pack_into(">QQ", raw, reserved + 16, 0x90000000, 1)
    else:
        raw[reserved + 16 : reserved + 16] = struct.pack(">QQ", 0x80010001, 1)
        header[1] += 16
        header[2] += 16
        header[3] += 16
        HEADER.pack_into(raw, 0, *header)
    with pytest.raises(ValueError, match=r"overlap|reservation"):
        decode_device_tree(bytes(raw))


def test_newer_compatible_version_accepted(compiled_tree: bytes) -> None:
    """Accept the unchanged v17 representation declared backwards compatible by a newer header.

    Parameters
    ----------
    compiled_tree
        Actual compiler-produced DTB.
    """
    raw = bytearray(compiled_tree)
    WORD.pack_into(raw, 5 * WORD.size, 18)
    WORD.pack_into(raw, 6 * WORD.size, 17)
    assert (
        decode_device_tree(bytes(raw)).nodes.keys()
        == decode_device_tree(compiled_tree).nodes.keys()
    )
