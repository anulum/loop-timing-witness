# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — compiled firmware and telemetry reservation admission

"""Exercise whole reservation admission on actual compiler-produced device trees."""

from __future__ import annotations

from dataclasses import replace

import pytest
from amp_memory import MemorySelection, ReservedMemory, bind_memory
from device_tree_resources import Region
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
RAM = "/memory@80000000"
FW = "/reserved-memory/firmware@80000000"
SHARED = "/reserved-memory/telemetry@80080000"
SELECTION = MemorySelection(RAM, FW, SHARED, 16496, 16384)
SOURCE = """/dts-v1/;
/ {
    #address-cells = <2>; #size-cells = <2>;
    memory@80000000 {
        device_type = "memory";
        reg = <0 0x80000000 0 0x100000>;
    };
    reserved-memory {
        #address-cells = <2>; #size-cells = <2>; ranges;
        firmware@80000000 { reg = <0 0x80000000 0 0x80000>; no-map; };
        telemetry@80080000 { reg = <0 0x80080000 0 0x10000>; no-map; };
        other@80090000 { reg = <0 0x80090000 0 0x1000>; };
    };
};
"""


def test_complete_reserved_extents(compile_tree: CompileTree) -> None:
    """Admit adjacent complete disjoint RAM reservations and matching header entries.

    Parameters
    ----------
    compile_tree
        Actual compiler and public binary decoder.
    """
    expected = ReservedMemory(Region(0x80000000, 0x80000), Region(0x80080000, 0x10000))
    assert bind_memory(compile_tree(SOURCE), SELECTION) == expected
    source = SOURCE.replace("/dts-v1/;", "/dts-v1/; /memreserve/ 0x80000000 0x80000;")
    assert bind_memory(compile_tree(source), SELECTION) == expected
    source = SOURCE.replace("/dts-v1/;", "/dts-v1/; /memreserve/ 0x90000000 0x1000;")
    assert bind_memory(compile_tree(source), SELECTION) == expected
    assert (
        bind_memory(compile_tree(SOURCE.replace("no-map;", 'no-map; status = "ok";')), SELECTION)
        == expected
    )
    second = '    memory@90000000 { device_type = "memory"; reg = <0 0x90000000 0 0x10000>; };\n'
    assert (
        bind_memory(
            compile_tree(SOURCE.replace("    reserved-memory {", second + "    reserved-memory {")),
            SELECTION,
        )
        == expected
    )


@pytest.mark.parametrize("address", ["0x80000000", "0x80040000", "0x80080000"])
def test_original_reservation_refuses_overlapping_second_ram_node(
    compile_tree: CompileTree, address: str
) -> None:
    """Refuse a second original RAM owner of any selected reserved extent.

    Parameters
    ----------
    compile_tree
        Actual device-tree compiler and public decoder.
    address
        Second RAM bank beginning in the firmware or telemetry reservation.
    """
    second = (
        f'    memory-secondary@{address[2:]} {{ device_type = "memory"; '
        f"reg = <0 {address} 0 0x10000>; }};\n"
    )
    tree = compile_tree(SOURCE.replace("    reserved-memory {", second + "    reserved-memory {"))
    with pytest.raises(ValueError, match="ambiguous original RAM"):
        bind_memory(tree, SELECTION)


@pytest.mark.parametrize(
    ("original", "replacement", "finding"),
    [
        ("ranges;", "", "empty ranges"),
        ("ranges;", "ranges = <0 0 0 0 0 0x100000>;", "empty ranges"),
        ("#size-cells = <2>; ranges;", "#size-cells = <1>; ranges;", "cell geometry"),
        ("no-map;", "", "unmapped"),
        ("no-map;", "no-map = <1>;", "unmapped"),
        ("no-map;", "no-map; reusable;", "non-reusable"),
        ("no-map;", 'no-map; status = "disabled";', "enabled"),
        ("0x80000000 0 0x80000", "0 0 0x80000", "nonzero page-aligned"),
        ("0x80000000 0 0x80000", "0x80000001 0 0x80000", "page-aligned"),
        ("0x80000000 0 0x80000", "0x80000000 0 0", "nonzero page-aligned"),
        ("0x80000000 0 0x80000", "0x80000000 0 0x80001", "page-aligned"),
        ("0x80000000 0 0x80000", "0x80000000 0 0x100000", "reservations overlap"),
        ("0x80000000 0 0x80000", "0x80000000 0 0x40000 0 0x80040000 0 0x40000", "one nonzero"),
        ('device_type = "memory";', 'device_type = "other";', "backing RAM"),
        ('device_type = "memory";', 'device_type = "memory"; status = "disabled";', "backing RAM"),
        ("0x80000000 0 0x100000", "0x80000000 0 0x70000", "complete unambiguous"),
        (
            "0x80000000 0 0x100000",
            "0x80000000 0 0x100000 0 0x80000000 0 0x100000",
            "complete unambiguous",
        ),
        (
            "other@80090000 { reg = <0 0x80090000 0 0x1000>;",
            "other@80090000 { reg = <0 0x80070000 0 0x20000>;",
            "another reserved",
        ),
        (
            "other@80090000 { reg = <0 0x80090000 0 0x1000>;",
            "other@80090000 { size = <0 0x1000>;",
            "property is absent",
        ),
        ("/dts-v1/;", "/dts-v1/; /memreserve/ 0x80001000 0x1000;", "unmatched original"),
    ],
)
def test_original_reservation_refusals(
    compile_tree: CompileTree, original: str, replacement: str, finding: str
) -> None:
    """Reject conflicting, malformed and partially covered original declared extents.

    Parameters
    ----------
    compile_tree
        Actual compiler and public binary decoder.
    original
        Original source fragment.
    replacement
        Invalid replacement declaration.
    finding
        Required public refusal diagnostic.
    """
    tree = compile_tree(SOURCE.replace(original, replacement))
    with pytest.raises(ValueError, match=finding):
        bind_memory(tree, SELECTION)


@pytest.mark.parametrize(
    "selection",
    [
        replace(SELECTION, shared_path=FW),
        replace(SELECTION, firmware_path="/absent"),
        replace(SELECTION, firmware_path=RAM),
        replace(SELECTION, ram_path="/absent"),
        replace(SELECTION, mailbox_bytes=True),
        replace(SELECTION, mailbox_bytes=0),
        replace(SELECTION, mailbox_bytes=65537),
        replace(SELECTION, stack_bytes=True),
        replace(SELECTION, stack_bytes=4095),
        replace(SELECTION, stack_bytes=4097),
        replace(SELECTION, stack_bytes=0x90000),
    ],
)
def test_invalid_requested_selection(compile_tree: CompileTree, selection: MemorySelection) -> None:
    """Refuse invalid explicit ownership paths and ABI or stack capacity requests.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    selection
        Invalid explicit build resource request.
    """
    with pytest.raises(ValueError, match=r"AMP|requested"):
        bind_memory(compile_tree(SOURCE), selection)


def test_missing_original_parent(compile_tree: CompileTree) -> None:
    """Refuse a decoded topology whose required reservation parent was removed.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    """
    tree = compile_tree(SOURCE)
    del tree.nodes["/reserved-memory"]
    with pytest.raises(ValueError, match="empty ranges"):
        bind_memory(tree, SELECTION)
