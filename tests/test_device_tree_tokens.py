# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — binary tree nesting and property corruption refusal

"""Refuse malformed binary trees through the complete public DTB decoder."""

from __future__ import annotations

import struct

import pytest
from device_tree_blob import decode_device_tree
from test_device_tree_blob import HEADER, WORD, compiled_tree

__all__ = ["compiled_tree"]

ROOT = WORD.pack(1) + b"\0\0\0\0"
CHILD = WORD.pack(1) + b"x\0\0\0"
CLOSE = WORD.pack(2)
END = WORD.pack(9)
NOP = WORD.pack(4)
PROPERTY = WORD.pack(3) + struct.pack(">II", 0, 0)


def replace_structure(content: bytes, structure: bytes) -> bytes:
    """Replace tokens within actual compiler output, preserving reservation and string blocks.

    Parameters
    ----------
    content
        Actual compiled DTB containing the original blocks.
    structure
        New token sequence to admit or refuse through the public decoder.

    Returns
    -------
    bytes
        Complete file with updated total, structure size and strings offset.
    """
    header = list(HEADER.unpack_from(content))
    start, size = header[2], header[9]
    delta = len(structure) - size
    header[1] += delta
    header[3] += delta
    header[9] = len(structure)
    raw = bytearray(content[:start] + structure + content[start + size :])
    HEADER.pack_into(raw, 0, *header)
    return bytes(raw)


@pytest.mark.parametrize(
    ("structure", "finding"),
    [
        (WORD.pack(1), "string offset"),
        (WORD.pack(1) + b"abcd", "unterminated"),
        (WORD.pack(1) + b"\xff\0\0\0", "ASCII"),
        (WORD.pack(1) + b"\0\x01\0\0", "padding"),
        (CHILD + CLOSE + END, "root"),
        (ROOT + WORD.pack(1) + b"a/b\0" + CLOSE + CLOSE + END, "child name"),
        (ROOT + CHILD + CLOSE + CHILD + CLOSE + CLOSE + END, "duplicate.*node"),
        (ROOT + CLOSE + ROOT + CLOSE + END, "root"),
        (ROOT + WORD.pack(3) + WORD.pack(0), "property header"),
        (ROOT + WORD.pack(3) + struct.pack(">II", 0, 0xFFFFFFFF) + CLOSE + END, "string offset"),
        (ROOT + WORD.pack(3) + struct.pack(">II", 0xFFFFFFFF, 0) + CLOSE + END, "property"),
        (ROOT + PROPERTY + PROPERTY + CLOSE + END, "duplicate.*property"),
        (PROPERTY + END, "outside a node"),
        (ROOT + CHILD + CLOSE + PROPERTY + CLOSE + END, "after a child"),
        (CLOSE + END, "unmatched"),
        (ROOT + END, "complete tree"),
        (END, "complete tree"),
        (ROOT + CLOSE + END + NOP, "termination"),
        (ROOT + WORD.pack(99) + CLOSE + END, "unknown"),
        (ROOT + CLOSE, "final end token"),
    ],
)
def test_malformed_tree_refused(compiled_tree: bytes, structure: bytes, finding: str) -> None:
    """Reject invalid real-file nesting, ordering, names, property bounds and termination.

    Parameters
    ----------
    compiled_tree
        Original actual compiler file retaining its property-name block.
    structure
        Corrupted token bytes replacing the original structure.
    finding
        Expected refusal diagnostic expression.
    """
    with pytest.raises(ValueError, match=finding):
        decode_device_tree(replace_structure(compiled_tree, structure))


def test_nops_empty_properties_and_padded_values(compiled_tree: bytes) -> None:
    """Decode legal NOPs and exact empty or non-word-sized property values.

    Parameters
    ----------
    compiled_tree
        Actual compiler bytes whose first string names the test property.
    """
    tree = decode_device_tree(
        replace_structure(compiled_tree, NOP + ROOT + PROPERTY + CLOSE + NOP + END)
    )
    assert list(tree.nodes["/"].properties.values()) == [b""]
    prop = WORD.pack(3) + struct.pack(">II", 1, 0) + b"x\0\0\0"
    tree = decode_device_tree(replace_structure(compiled_tree, ROOT + prop + CLOSE + END))
    assert list(tree.nodes["/"].properties.values()) == [b"x"]


def test_multiple_nonoverlapping_reservations(compiled_tree: bytes) -> None:
    """Retain adjacent physical reservations as distinct original entries.

    Parameters
    ----------
    compiled_tree
        Actual compiler output containing one original reservation.
    """
    raw = bytearray(compiled_tree)
    header = list(HEADER.unpack_from(raw))
    offset = header[4] + 16
    raw[offset:offset] = struct.pack(">QQ", 0x80020000, 0x10000)
    header[1] += 16
    header[2] += 16
    header[3] += 16
    HEADER.pack_into(raw, 0, *header)
    assert decode_device_tree(bytes(raw)).reservations == (
        (0x80010000, 0x10000),
        (0x80020000, 0x10000),
    )


@pytest.mark.parametrize("variant", ["depth", "nodes", "path"])
def test_excessive_tree_resources_refused(compiled_tree: bytes, variant: str) -> None:
    """Bound nesting, node counts and expanded paths before unbounded object growth.

    Parameters
    ----------
    compiled_tree
        Real compiled file retaining valid block and reservation layout.
    variant
        Structurally valid tree exceeding one declared parser resource bound.
    """
    if variant == "depth":
        structure = ROOT + CHILD * 64 + CLOSE * 65 + END
    elif variant == "path":
        name = b"x" * 4096 + b"\0\0\0\0"
        structure = ROOT + WORD.pack(1) + name + CLOSE + CLOSE + END
    else:
        children = []
        for index in range(16384):
            name = str(index).encode("ascii") + b"\0"
            name += b"\0" * (-len(name) % WORD.size)
            children.append(WORD.pack(1) + name + CLOSE)
        structure = ROOT + b"".join(children) + CLOSE + END
    with pytest.raises(ValueError, match="parser resource limit"):
        decode_device_tree(replace_structure(compiled_tree, structure))
