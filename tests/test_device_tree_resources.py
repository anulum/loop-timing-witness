# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — compiled device-tree address translation and resource refusal

"""Exercise physical extent decoding from real compiled nested bus descriptions."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from device_tree_blob import DeviceTree, decode_device_tree
from device_tree_resources import Region, property_cells, register_regions

if TYPE_CHECKING:
    from pathlib import Path

CompileTree = Callable[[str], DeviceTree]
SOURCE = """/dts-v1/;
/ {
    #address-cells = <2>;
    #size-cells = <2>;
    bus@40000000 {
        #address-cells = <1>;
        #size-cells = <1>;
        ranges = <0 0 0x40000000 0x1000>;
        device@100 { reg = <0x100 0x100>; };
        nested {
            #address-cells = <1>;
            #size-cells = <1>;
            ranges;
            device@200 { reg = <0x200 0x100>; };
        };
    };
    memory@80000000 { reg = <0 0x80000000 0 0x100000>; };
};
"""


@pytest.fixture
def compile_tree(tmp_path: Path) -> CompileTree:
    """Compile each supplied source and decode the actual DTB through the public API.

    Parameters
    ----------
    tmp_path
        Exact owned source and binary output directory.

    Returns
    -------
    CompileTree
        Real dtc compilation followed by original-byte decoding.
    """
    compiler = shutil.which("dtc")
    assert compiler is not None, "dtc is required for actual platform resource tests"

    def compile_source(source: str) -> DeviceTree:
        """Produce a decoded tree from a real compiler invocation.

        Parameters
        ----------
        source
            Complete DTS input for this resource case.

        Returns
        -------
        DeviceTree
            Original successfully compiled topology.
        """
        source_path = tmp_path / "platform.dts"
        binary = tmp_path / "platform.dtb"
        source_path.write_text(source, encoding="ascii")
        subprocess.run(
            [compiler, "-I", "dts", "-O", "dtb", "-o", str(binary), str(source_path)],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return decode_device_tree(binary.read_bytes())

    return compile_source


def test_actual_nested_translation(compile_tree: CompileTree) -> None:
    """Resolve direct RAM, mapped MMIO and nested identity mappings to physical extents.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder entry point.
    """
    tree = compile_tree(SOURCE)
    assert register_regions(tree, "/memory@80000000") == (Region(0x80000000, 0x100000),)
    assert register_regions(tree, "/bus@40000000/device@100") == (Region(0x40000100, 0x100),)
    assert register_regions(tree, "/bus@40000000/nested/device@200") == (Region(0x40000200, 0x100),)


@pytest.mark.parametrize(
    ("original", "replacement", "finding"),
    [
        ("reg = <0x100 0x100>;", "", "property is absent"),
        ("#address-cells = <1>;", "#address-cells = <0>;", "cell geometry"),
        ("#address-cells = <1>;", "#address-cells = <3>;", "cell count"),
        ("#address-cells = <1>;", "#address-cells = <1 1>;", "cell count"),
        ("reg = <0x100 0x100>;", "reg;", "cell geometry"),
        ("reg = <0x100 0x100>;", "reg = <0x100>;", "cell geometry"),
        ("reg = <0x100 0x100>;", "reg = [01];", "whole number of cells"),
        ("ranges = <0 0 0x40000000 0x1000>;", "", "lacks an address translation"),
        ("ranges = <0 0 0x40000000 0x1000>;", "ranges = <0 0>;", "cell geometry"),
        ("reg = <0x100 0x100>;", "reg = <0xFFF 0x100>;", "unique complete bus mapping"),
        (
            "ranges = <0 0 0x40000000 0x1000>;",
            "ranges = <0 0 0x40000000 0x1000 0 0 0x50000000 0x1000>;",
            "unique complete bus mapping",
        ),
    ],
)
def test_invalid_mmio_mapping_refused(
    compile_tree: CompileTree, original: str, replacement: str, finding: str
) -> None:
    """Reject malformed or ambiguous mappings in actual compiler-produced trees.

    Parameters
    ----------
    compile_tree
        Real source-to-decoded-tree compiler.
    original
        Original DTS fragment to replace.
    replacement
        Invalid declared geometry or mapping.
    finding
        Required public refusal diagnostic.
    """
    tree = compile_tree(SOURCE.replace(original, replacement))
    with pytest.raises(ValueError, match=finding):
        register_regions(tree, "/bus@40000000/device@100")


def test_unavailable_node_and_root_refused(compile_tree: CompileTree) -> None:
    """Reject unknown explicit resource paths and the root's absent register property.

    Parameters
    ----------
    compile_tree
        Actual compiler and decoder entry point.
    """
    tree = compile_tree(SOURCE)
    for path in ["/", "/absent"]:
        with pytest.raises(ValueError, match="node or property is absent"):
            register_regions(tree, path)


def test_standard_defaults_and_zero_size(compile_tree: CompileTree) -> None:
    """Interpret absent parent cell declarations using standard defaults and explicit zero sizes.

    Parameters
    ----------
    compile_tree
        Actual DTS compiler and decoder.
    """
    tree = compile_tree("/dts-v1/; / { device@100 { reg = <0 0x100 0x10>; }; };")
    assert register_regions(tree, "/device@100") == (Region(0x100, 0x10),)
    tree = compile_tree(
        "/dts-v1/; / { #address-cells = <1>; #size-cells = <0>; device@1 { reg = <1>; }; };"
    )
    assert register_regions(tree, "/device@1") == (Region(1, 0),)
    assert property_cells(b"") == ()


def test_physical_address_overflow_refused(compile_tree: CompileTree) -> None:
    """Refuse RV64 extent overflow and a mapping extending past a 32-bit parent.

    Parameters
    ----------
    compile_tree
        Real compiler and decoded topology entry point.
    """
    tree = compile_tree(SOURCE.replace("0 0x80000000 0 0x100000", "0xFFFFFFFF 0xFFFFFFFF 0 2"))
    with pytest.raises(ValueError, match="RV64 or declared bus address space"):
        register_regions(tree, "/memory@80000000")
    tree = compile_tree(
        "/dts-v1/; / { #address-cells = <1>; #size-cells = <1>; "
        "device@ffffffff { reg = <0xFFFFFFFF 2>; }; };"
    )
    with pytest.raises(ValueError, match="declared bus address space"):
        register_regions(tree, "/device@ffffffff")
    source = SOURCE.replace("#address-cells = <2>;", "#address-cells = <1>;")
    tree = compile_tree(source.replace("<0 0 0x40000000 0x1000>", "<0 0xFFFFFF00 0x1000>"))
    with pytest.raises(ValueError, match="parent address space"):
        register_regions(tree, "/bus@40000000/device@100")
