# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — unambiguous scalar string and phandle properties

"""Interpret original property encodings before resolving platform references."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .device_tree_resources import property_cells

if TYPE_CHECKING:
    from .device_tree_blob import DeviceTree
    from .device_tree_structure import Node

INVALID_PHANDLE = (1 << 32) - 1


def single_cell(node: Node, name: str) -> int:
    """Require exactly one original unsigned cell for a named property.

    Parameters
    ----------
    node
        Original node containing the requested property.
    name
        Exact property name, with no default fallback.

    Returns
    -------
    int
        Declared 32-bit unsigned scalar.

    Raises
    ------
    ValueError
        If the property is absent, truncated or not a scalar.
    """
    if name not in node.properties:
        message = f"device-tree scalar property is absent: {node.path}:{name}"
        raise ValueError(message)
    values = property_cells(node.properties[name])
    if len(values) != 1:
        message = f"device-tree property is not one scalar: {node.path}:{name}"
        raise ValueError(message)
    return values[0]


def string_list(node: Node, name: str) -> tuple[str, ...]:
    """Require a terminated ASCII string list without empty elements.

    Parameters
    ----------
    node
        Original node containing the named property.
    name
        Exact property name to decode.

    Returns
    -------
    tuple of str
        Declared strings in their original order.

    Raises
    ------
    ValueError
        If data is absent, unterminated, empty or not ASCII.
    """
    content = node.properties.get(name, b"")
    if not content or not content.endswith(b"\0"):
        message = f"device-tree string property is absent or unterminated: {node.path}:{name}"
        raise ValueError(message)
    try:
        values = tuple(content[:-1].decode("ascii").split("\0"))
    except UnicodeDecodeError as error:
        message = f"device-tree property string is not ASCII: {node.path}:{name}"
        raise ValueError(message) from error
    if not all(values):
        message = f"device-tree string property contains an empty element: {node.path}:{name}"
        raise ValueError(message)
    return values


def phandle_nodes(tree: DeviceTree) -> dict[int, Node]:
    """Resolve globally unique phandles and refuse conflicting legacy aliases.

    Parameters
    ----------
    tree
        Original decoded topology, including unreferenced nodes.

    Returns
    -------
    dict of int to Node
        Exact declared reference identifiers and their unique nodes.

    Raises
    ------
    ValueError
        If any phandle is invalid, duplicated or disagrees with its legacy alias.
    """
    result: dict[int, Node] = {}
    for node in tree.nodes.values():
        aliases = [
            single_cell(node, name)
            for name in ("phandle", "linux,phandle")
            if name in node.properties
        ]
        if not aliases:
            continue
        handle = aliases[0]
        if handle in (0, INVALID_PHANDLE) or any(value != handle for value in aliases):
            message = "device-tree phandle is reserved or disagrees with its legacy alias"
            raise ValueError(message)
        if handle in result:
            message = "device-tree phandle references multiple nodes"
            raise ValueError(message)
        result[handle] = node
    return result
