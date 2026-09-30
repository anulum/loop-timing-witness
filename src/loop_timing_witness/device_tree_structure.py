# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded flattened device-tree structure decoding

"""Decode actual FDT node/property tokens without interpreting platform ownership."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

WORD = struct.Struct(">I")
PROPERTY = struct.Struct(">II")
ALIGNMENT = 4
MAX_DEPTH = 64
MAX_NODES = 16384
MAX_PATH_CHARACTERS = 4096


class Token(IntEnum):
    """Version-17 structure tokens specified by the Devicetree Specification."""

    BEGIN_NODE = 1
    END_NODE = 2
    PROPERTY = 3
    NOP = 4
    END = 9


@dataclass
class Node:
    """One decoded node, retaining uninterpreted property bytes.

    Parameters
    ----------
    path
        Absolute unique node path; the root is ``/``.
    properties
        Property names and exact value bytes.
    """

    path: str
    properties: dict[str, bytes] = field(default_factory=dict)


def terminated_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read one bounded ASCII string, including its terminating byte.

    Parameters
    ----------
    data
        Exact containing block bytes.
    offset
        Start offset within the containing block.

    Returns
    -------
    tuple of str and int
        Decoded text and offset immediately after its terminator.

    Raises
    ------
    ValueError
        If the offset, terminator or ASCII encoding is invalid.
    """
    if not 0 <= offset < len(data):
        message = "device-tree string offset outside its block"
        raise ValueError(message)
    end = data.find(b"\0", offset)
    if end < 0:
        message = "unterminated device-tree string"
        raise ValueError(message)
    try:
        return data[offset:end].decode("ascii"), end + 1
    except UnicodeDecodeError as error:
        message = "device-tree name is not ASCII"
        raise ValueError(message) from error


def aligned_offset(data: bytes, offset: int) -> int:
    """Validate zero padding and advance to the next structure word.

    Parameters
    ----------
    data
        Exact structure block bytes.
    offset
        First padding byte after a name or property value.

    Returns
    -------
    int
        Next aligned token offset.

    Raises
    ------
    ValueError
        If padding is truncated or contains nonzero bytes.
    """
    aligned = (offset + ALIGNMENT - 1) & ~(ALIGNMENT - 1)
    if aligned > len(data) or any(data[offset:aligned]):
        message = "invalid device-tree structure padding"
        raise ValueError(message)
    return aligned


def _property(data: bytes, strings: bytes, offset: int, node: Node) -> int:
    """Retain one complete uniquely named property before any child node.

    Parameters
    ----------
    data
        Structure block bytes.
    strings
        Property-name block bytes.
    offset
        Offset immediately after the property token.
    node
        Current node receiving the decoded property.

    Returns
    -------
    int
        Next aligned token offset.

    Raises
    ------
    ValueError
        If the property header, name, extent or uniqueness is invalid.
    """
    if offset + PROPERTY.size > len(data):
        message = "truncated device-tree property header"
        raise ValueError(message)
    size, name_offset = PROPERTY.unpack_from(data, offset)
    start = offset + PROPERTY.size
    name, _ = terminated_string(strings, name_offset)
    if not name or "/" in name or name in node.properties or size > len(data) - start:
        message = "invalid or duplicate device-tree property"
        raise ValueError(message)
    node.properties[name] = data[start : start + size]
    return aligned_offset(data, start + size)


def _begin_node(
    data: bytes, offset: int, nodes: dict[str, Node], stack: list[Node], parents: set[str]
) -> int:
    """Admit a uniquely named root or child and retain its nesting context.

    Parameters
    ----------
    data
        Structure block bytes.
    offset
        Start of the node name after its token.
    nodes
        Existing absolute paths, receiving the new node.
    stack
        Open ancestor nodes, receiving the new nesting level.
    parents
        Nodes whose property lists have ended because a child began.

    Returns
    -------
    int
        Next aligned token offset.

    Raises
    ------
    ValueError
        If the name, root count, path uniqueness or padding is invalid.
    """
    if len(stack) >= MAX_DEPTH or len(nodes) >= MAX_NODES:
        message = "device-tree depth or node count exceeds the parser resource limit"
        raise ValueError(message)
    name, offset = terminated_string(data, offset)
    if (not stack and (name or nodes)) or (stack and (not name or "/" in name)):
        message = "invalid device-tree root or child name"
        raise ValueError(message)
    path = stack[-1].path.rstrip("/") + "/" + name if stack else "/"
    if len(path) > MAX_PATH_CHARACTERS:
        message = "device-tree node path exceeds the parser resource limit"
        raise ValueError(message)
    if path in nodes:
        message = "duplicate device-tree node path"
        raise ValueError(message)
    node = Node(path)
    nodes[path] = node
    if stack:
        parents.add(stack[-1].path)
    stack.append(node)
    return aligned_offset(data, offset)


def decode_structure(data: bytes, strings: bytes) -> dict[str, Node]:
    """Decode one complete tree with unique paths and ordered properties.

    Parameters
    ----------
    data
        Exact version-17-compatible structure block.
    strings
        Exact property-name block.

    Returns
    -------
    dict of str to Node
        Absolute paths mapped to nodes and original property bytes.

    Raises
    ------
    ValueError
        If tokens, nesting, names, ordering, padding or termination are invalid.
    """
    nodes: dict[str, Node] = {}
    stack: list[Node] = []
    parents_with_children: set[str] = set()
    offset = 0
    while offset + WORD.size <= len(data):
        token = WORD.unpack_from(data, offset)[0]
        offset += WORD.size
        if token == Token.NOP:
            continue
        if token == Token.BEGIN_NODE:
            offset = _begin_node(data, offset, nodes, stack, parents_with_children)
        elif token == Token.PROPERTY:
            if not stack or stack[-1].path in parents_with_children:
                message = "device-tree property outside a node or after a child"
                raise ValueError(message)
            offset = _property(data, strings, offset, stack[-1])
        elif token == Token.END_NODE:
            if not stack:
                message = "unmatched device-tree node end"
                raise ValueError(message)
            stack.pop()
        elif token == Token.END:
            if stack or not nodes or offset != len(data):
                message = "device-tree end precedes complete tree termination"
                raise ValueError(message)
            return nodes
        else:
            message = "unknown device-tree structure token"
            raise ValueError(message)
    message = "device-tree structure lacks its final end token"
    raise ValueError(message)
