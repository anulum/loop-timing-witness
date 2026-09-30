# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original MMIO aliases and interrupt consumer collision tests

"""Exercise collision admission through the real compiled device-binding entry point."""

from __future__ import annotations

import pytest
from amp_device import bind_device
from test_amp_device import PATH, SELECTION, SOURCE
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
CONTROLLER = """
    other-controller { phandle = <200>; #interrupt-cells = <2>; interrupt-controller; };
"""


@pytest.mark.parametrize(
    "declaration",
    [
        "other { interrupt-parent = <100>; interrupts = <40>; };",
        "other { interrupt-parent = <100>; interrupts = <1 40 3>; };",
        "other { interrupts-extended = <200 7 8 100 40>; };",
        'other { interrupt-parent = <100>; interrupts = <40>; status = "disabled"; };',
    ],
)
def test_duplicate_original_source(compile_tree: CompileTree, declaration: str) -> None:
    """Refuse duplicate source consumers including disabled and mixed-width declarations.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    declaration
        Another original source consumer.
    """
    tree = compile_tree(SOURCE.replace("    soc {", CONTROLLER + declaration + "    soc {"))
    with pytest.raises(ValueError, match="another original consumer"):
        bind_device(tree, PATH, SELECTION)


@pytest.mark.parametrize(
    ("declaration", "finding"),
    [
        ("other { interrupts = <1>; };", "lacks an original parent"),
        ("other { interrupt-parent = <999>; interrupts = <1>; };", "undeclared parent"),
        ("other { interrupt-parent = <200>; interrupts = <1>; };", "specifier geometry"),
        ("other { interrupt-parent = <100>; interrupts; };", "specifier geometry"),
        ("other { interrupts-extended = <999 1>; };", "undeclared controller"),
        ("other { interrupts-extended = <200 1>; };", "truncated"),
        ("other { interrupts = <1>; interrupts-extended = <100 1>; };", "ambiguous"),
    ],
)
def test_unresolved_consumer_refused(
    compile_tree: CompileTree, declaration: str, finding: str
) -> None:
    """Reject unresolved direct consumer geometry rather than silently missing collisions.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    declaration
        Malformed additional consumer.
    finding
        Required public refusal diagnostic.
    """
    tree = compile_tree(SOURCE.replace("    soc {", CONTROLLER + declaration + "    soc {"))
    with pytest.raises(ValueError, match=finding):
        bind_device(tree, PATH, SELECTION)


@pytest.mark.parametrize("width", [0, 5])
def test_unsupported_controller_width(compile_tree: CompileTree, width: int) -> None:
    """Reject controller specifier widths outside the explicit supported bounds.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    width
        Unsupported original controller width.
    """
    declaration = CONTROLLER.replace("<2>", f"<{width}>")
    source = SOURCE.replace(
        "    soc {", declaration + "other { interrupts-extended = <200 1>; }; soc {"
    )
    with pytest.raises(ValueError, match="bounded direct controller"):
        bind_device(compile_tree(source), PATH, SELECTION)


def test_unresolved_interrupt_nexus(compile_tree: CompileTree) -> None:
    """Refuse a reference to an interrupt nexus without a direct controller marker.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    """
    declaration = CONTROLLER.replace("interrupt-controller;", "")
    source = SOURCE.replace(
        "    soc {", declaration + "other { interrupts-extended = <200 1 2>; }; soc {"
    )
    with pytest.raises(ValueError, match="bounded direct controller"):
        bind_device(compile_tree(source), PATH, SELECTION)


@pytest.mark.parametrize(
    "declaration",
    [
        'memory@40000000 { device_type = "memory"; reg = <0 0x40000000 0 0x100000>; };',
        "other@40000080 { reg = <0 0x40000080 0 256>; };",
        (
            "bus { #address-cells = <1>; #size-cells = <1>; "
            "ranges = <0 0 0x40000000 4096>; other@80 { reg = <128 256>; }; };"
        ),
    ],
)
def test_complete_physical_resource_overlap(compile_tree: CompileTree, declaration: str) -> None:
    """Refuse whole RAM and translated register extents intersecting the selected aperture.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    declaration
        Colliding original physical resource.
    """
    source = SOURCE.replace("    soc {", declaration + "    soc {")
    with pytest.raises(ValueError, match="another original physical resource"):
        bind_device(compile_tree(source), PATH, SELECTION)


def test_disjoint_and_nonphysical_resources(compile_tree: CompileTree) -> None:
    """Admit adjacent physical extents, independent interrupts and non-MMIO bus identifiers.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    """
    declaration = (
        CONTROLLER
        + """
    other@40000100 { reg = <0 0x40000100 0 256>; interrupts = <1 3>; };
    other { interrupts-extended = <200 7 8 100 1>; };
    peripheral-bus { #address-cells = <1>; #size-cells = <0>; endpoint@40 { reg = <64>; }; };
    """
    )
    tree = compile_tree(
        SOURCE.replace("/ {", "/ { interrupt-parent = <100>;", 1).replace(
            "    soc {", declaration + "    soc {"
        )
    )
    assert bind_device(tree, PATH, SELECTION).aperture.address == 0x40000000


def test_mmio_header_reservation_refused(compile_tree: CompileTree) -> None:
    """Reject original header reservations intersecting the complete AXI aperture.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    """
    source = SOURCE.replace("/dts-v1/;", "/dts-v1/; /memreserve/ 0x40000080 128;")
    with pytest.raises(ValueError, match="original header reservation"):
        bind_device(compile_tree(source), PATH, SELECTION)
