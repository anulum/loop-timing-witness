# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original property and global reference refusal tests

"""Exercise scalar/string/referral APIs against actual compiled tree objects."""

from __future__ import annotations

import struct

import pytest
from device_tree_properties import phandle_nodes, single_cell, string_list
from test_device_tree_interrupts import INTC, PLIC, SOURCE
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]


@pytest.mark.parametrize("value", [None, b"", b"x", struct.pack(">2I", 1, 2)])
def test_invalid_scalar_property_refused(compile_tree: CompileTree, value: bytes | None) -> None:
    """Refuse absent, empty, truncated and multiple-value scalar input fields.

    Parameters
    ----------
    compile_tree
        Actual topology compiler and decoder.
    value
        Corrupted property encoding, or removal.
    """
    tree = compile_tree(SOURCE)
    if value is None:
        del tree.nodes[PLIC].properties["riscv,ndev"]
    else:
        tree.nodes[PLIC].properties["riscv,ndev"] = value
    with pytest.raises(ValueError, match=r"scalar|whole number of cells"):
        single_cell(tree.nodes[PLIC], "riscv,ndev")


@pytest.mark.parametrize("value", [None, b"", b"unterminated", b"\xff\0", b"\0", b"valid\0\0"])
def test_invalid_string_list_refused(compile_tree: CompileTree, value: bytes | None) -> None:
    """Refuse incomplete encodings, invalid ASCII and empty list elements.

    Parameters
    ----------
    compile_tree
        Actual compiler and decoded public node properties.
    value
        Invalid list bytes, or removal.
    """
    tree = compile_tree(SOURCE)
    if value is None:
        del tree.nodes[PLIC].properties["compatible"]
    else:
        tree.nodes[PLIC].properties["compatible"] = value
    with pytest.raises(ValueError, match="string"):
        string_list(tree.nodes[PLIC], "compatible")


@pytest.mark.parametrize("value", [0, 0xFFFFFFFF, 10])
def test_reserved_and_duplicate_phandles_refused(compile_tree: CompileTree, value: int) -> None:
    """Reject reserved reference identifiers and an identifier already owned by another CPU.

    Parameters
    ----------
    compile_tree
        Actual compiler-produced topology and decoder.
    value
        Reserved or duplicated identifier replacing CPU1's original reference.
    """
    tree = compile_tree(SOURCE)
    tree.nodes[INTC].properties["phandle"] = struct.pack(">I", value)
    with pytest.raises(ValueError, match="phandle"):
        phandle_nodes(tree)


def test_legacy_alias_consistency(compile_tree: CompileTree) -> None:
    """Resolve matching modern/legacy references and a legacy-only node; refuse conflicting aliases.

    Parameters
    ----------
    compile_tree
        Actual compiled topology and original property bytes.
    """
    tree = compile_tree(SOURCE)
    tree.nodes[INTC].properties["linux,phandle"] = struct.pack(">I", 20)
    assert phandle_nodes(tree)[20] is tree.nodes[INTC]
    del tree.nodes[INTC].properties["phandle"]
    assert phandle_nodes(tree)[20] is tree.nodes[INTC]
    tree.nodes[INTC].properties["phandle"] = struct.pack(">I", 21)
    with pytest.raises(ValueError, match="legacy alias"):
        phandle_nodes(tree)
