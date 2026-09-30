# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual device interrupt and aperture admission tests

"""Exercise versioned AXI device binding using actual DTB compiler output."""

from __future__ import annotations

import pytest
from amp_device import WitnessDevice, bind_device
from device_tree_interrupts import PlicSelection, bind_plic
from device_tree_resources import Region
from test_device_tree_interrupts import PLIC
from test_device_tree_interrupts import SOURCE as PLIC_SOURCE
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
PATH = "/witness@40000000"
SELECTION = PlicSelection(PLIC, 1, 40, "sifive")
DECLARATION = """
    witness@40000000 {
        compatible = "anulum,loop-timing-witness-axi-v1";
        reg = <0 0x40000000 0 256>;
        interrupt-parent = <100>; interrupts = <40>;
    };
"""
SOURCE = PLIC_SOURCE.replace("    soc {", DECLARATION + "    soc {")


def test_actual_interrupt_forms(compile_tree: CompileTree) -> None:
    """Resolve explicit, inherited and extended original single-source wiring.

    Parameters
    ----------
    compile_tree
        Actual dtc compiler and public binary decoder.
    """
    variants = [
        SOURCE,
        SOURCE.replace(
            "interrupt-parent = <100>; interrupts = <40>;", "interrupts-extended = <100 40>;"
        ),
        SOURCE.replace(
            "interrupt-parent = <100>; interrupts = <40>;", "interrupts = <40>;"
        ).replace("/ {", "/ { interrupt-parent = <100>;", 1),
    ]
    for source in variants:
        tree = compile_tree(source)
        expected = WitnessDevice(Region(0x40000000, 256), bind_plic(tree, SELECTION))
        assert bind_device(tree, PATH, SELECTION) == expected


@pytest.mark.parametrize(
    ("original", "replacement", "finding"),
    [
        (
            'compatible = "anulum,loop-timing-witness-axi-v1";',
            'compatible = "other";',
            "versioned AXI",
        ),
        (
            'compatible = "anulum,loop-timing-witness-axi-v1";',
            'compatible = "anulum,loop-timing-witness-axi-v1"; status = "disabled";',
            "enabled",
        ),
        ("interrupt-parent = <100>;", "interrupt-parent = <999>;", "undeclared controller"),
        ("interrupt-parent = <100>;", "", "lacks an original"),
        ("interrupt-parent = <100>;", "interrupt-parent = <10>;", "selected PLIC"),
        ("interrupts = <40>;", "interrupts = <41>;", "selected PLIC"),
        (
            "interrupt-parent = <100>; interrupts = <40>;",
            "interrupts-extended = <100>;",
            "exactly one",
        ),
        (
            "interrupt-parent = <100>; interrupts = <40>;",
            "interrupts-extended = <999 40>;",
            "selected PLIC",
        ),
        (
            "interrupt-parent = <100>; interrupts = <40>;",
            "interrupts-extended = <100 41>;",
            "selected PLIC",
        ),
        ("interrupts = <40>;", "interrupts = <40>; interrupts-extended = <100 40>;", "ambiguous"),
        ("interrupts = <40>;", "interrupts-extended = <100 40>;", "ambiguous"),
        ("reg = <0 0x40000000 0 256>;", "reg = <0 0x40000000 0 128>;", "256-byte"),
        ("reg = <0 0x40000000 0 256>;", "reg = <0 0x40000001 0 256>;", "aligned"),
        ("reg = <0 0x40000000 0 256>;", "reg = <0 0 0 256>;", "aligned"),
        (
            "reg = <0 0x40000000 0 256>;",
            "reg = <0 0x40000000 0 256 0 0x40000100 0 256>;",
            "one aligned",
        ),
        ("reg = <0 0x40000000 0 256>;", "reg = <0 0xc000000 0 256>;", "overlaps the PLIC"),
    ],
)
def test_original_device_refusals(
    compile_tree: CompileTree, original: str, replacement: str, finding: str
) -> None:
    """Reject malformed versioned identity, source wiring and full MMIO apertures.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    original
        Original input fragment to replace.
    replacement
        Invalid declared resource.
    finding
        Required public refusal diagnostic.
    """
    with pytest.raises(ValueError, match=finding):
        bind_device(compile_tree(SOURCE.replace(original, replacement)), PATH, SELECTION)


def test_absent_selected_device(compile_tree: CompileTree) -> None:
    """Reject an explicit path absent from original topology.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    """
    with pytest.raises(ValueError, match="versioned AXI"):
        bind_device(compile_tree(SOURCE), "/absent", SELECTION)
