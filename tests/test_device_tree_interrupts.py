# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual PLIC topology and machine-context resource validation

"""Exercise dedicated PLIC binding on real compiled topology and corrupted property inputs."""

from __future__ import annotations

import struct

import pytest
from device_tree_interrupts import PlicRegisters, PlicSelection, bind_plic
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
PLIC = "/soc/plic@c000000"
CPU = "/cpus/cpu@1"
INTC = CPU + "/interrupt-controller"
WORD = struct.Struct(">I")
SOURCE = """/dts-v1/;
/ {
    #address-cells = <2>;
    #size-cells = <2>;
    model = "ucbbar,spike-bare";
    cpus {
        #address-cells = <1>;
        #size-cells = <0>;
        cpu@0 {
            device_type = "cpu"; reg = <0>;
            intc0: interrupt-controller {
                compatible = "riscv,cpu-intc";
                #interrupt-cells = <1>; interrupt-controller; phandle = <10>;
            };
        };
        cpu@1 {
            device_type = "cpu"; reg = <1>;
            intc1: interrupt-controller {
                compatible = "riscv,cpu-intc";
                #interrupt-cells = <1>; interrupt-controller; phandle = <20>;
            };
        };
        cpu@2 {
            device_type = "cpu"; reg = <2>;
            intc2: interrupt-controller {
                compatible = "riscv,cpu-intc";
                #interrupt-cells = <1>; interrupt-controller; phandle = <30>;
            };
        };
    };
    soc {
        #address-cells = <2>; #size-cells = <2>; ranges;
        plic@c000000 {
            compatible = "sifive,plic-1.0.0", "riscv,plic0";
            #interrupt-cells = <1>; #address-cells = <0>; interrupt-controller;
            riscv,ndev = <64>; phandle = <100>;
            reg = <0 0xc000000 0 0x4000000>;
            interrupts-extended = <&intc0 11 &intc1 0xffffffff &intc1 11
                                   &intc1 9 &intc2 11 &intc2 9>;
        };
    };
};
"""


def test_original_context_order_and_source_word(compile_tree: CompileTree) -> None:
    """Preserve disabled-context positions and resolve the source's second enable word.

    Parameters
    ----------
    compile_tree
        Actual dtc compilation and complete DTB decoding.
    """
    tree = compile_tree(SOURCE)
    expected = PlicRegisters(2, 0xC0000A0, 0xC002104, 0xC202000, 0xC202004)
    assert bind_plic(tree, PlicSelection(PLIC, 1, 40, "sifive")) == expected
    assert bind_plic(tree, PlicSelection(PLIC, 1, 40, "spike")) == expected
    assert bind_plic(tree, PlicSelection(PLIC, 2, 1, "sifive")).context == 4


@pytest.mark.parametrize(
    ("hart", "source", "path"),
    [
        (0, 1, PLIC),
        (5, 1, PLIC),
        (True, 1, PLIC),
        (1, 0, PLIC),
        (1, 1024, PLIC),
        (1, True, PLIC),
        (1, 1, "/absent"),
    ],
)
def test_invalid_selection_refused(
    compile_tree: CompileTree, hart: int, source: int, path: str
) -> None:
    """Refuse invalid explicit hart, source and controller-path requests.

    Parameters
    ----------
    compile_tree
        Real topology compiler.
    hart
        Invalid or otherwise valid hardware identifier.
    source
        Invalid or otherwise valid source identifier.
    path
        Original or absent controller path.
    """
    with pytest.raises(ValueError, match=r"selection.*bounds"):
        bind_plic(compile_tree(SOURCE), PlicSelection(path, hart, source, "sifive"))


@pytest.mark.parametrize(
    ("path", "name", "value", "finding"),
    [
        (PLIC, "compatible", b"riscv,plic0\0", "concrete register layout"),
        (PLIC, "interrupt-controller", None, "geometry"),
        (PLIC, "#interrupt-cells", WORD.pack(2), "geometry"),
        (PLIC, "riscv,ndev", WORD.pack(0), "source"),
        (PLIC, "riscv,ndev", WORD.pack(1024), "source"),
        (PLIC, "reg", struct.pack(">4I", 0, 0, 0, 0x4000000), "nonzero"),
        (PLIC, "reg", struct.pack(">4I", 0, 0xC000001, 0, 0x4000000), "aligned"),
        (PLIC, "reg", struct.pack(">4I", 0, 0xC000000, 0, 0x100), "aperture"),
        (PLIC, "interrupts-extended", b"", "array"),
        (PLIC, "interrupts-extended", WORD.pack(20), "array"),
        (PLIC, "interrupts-extended", struct.pack(">2I", 99, 11), "undeclared phandle"),
        (PLIC, "interrupts-extended", struct.pack(">2I", 20, 1), "unsupported CPU interrupt"),
        (PLIC, "interrupts-extended", struct.pack(">2I", 20, 9), "unique.*machine context"),
        (
            PLIC,
            "interrupts-extended",
            struct.pack(">4I", 20, 11, 20, 11),
            "unique.*machine context",
        ),
        pytest.param(
            PLIC,
            "interrupts-extended",
            struct.pack(">2I", 20, 11) * 15873,
            "bounds",
            id="context-array-too-large",
        ),
        (INTC, "compatible", b"other\0", "RISC-V CPU"),
        (INTC, "#interrupt-cells", WORD.pack(2), "RISC-V CPU"),
        (INTC, "interrupt-controller", None, "RISC-V CPU"),
        (CPU, "device_type", b"other\0", "not an original CPU"),
        (CPU, "reg", b"", "identifier.*geometry"),
        ("/cpus", "#address-cells", WORD.pack(3), "identifier.*geometry"),
        ("/cpus", "#size-cells", WORD.pack(1), "identifier.*geometry"),
        ("/cpus/cpu@2", "reg", WORD.pack(1), "multiple CPUs"),
    ],
)
def test_corrupt_binding_properties_refused(
    compile_tree: CompileTree, path: str, name: str, value: bytes | None, finding: str
) -> None:
    """Refuse semantic corruption of original compiled public topology properties.

    Parameters
    ----------
    compile_tree
        Actual DTS compiler and public decoded topology.
    path
        Existing node whose original property is altered.
    name
        Exact field to replace or remove from the public input object.
    value
        Corrupted raw property bytes, or removal.
    finding
        Expected complete public binding refusal.
    """
    tree = compile_tree(SOURCE)
    if value is None:
        del tree.nodes[path].properties[name]
    else:
        tree.nodes[path].properties[name] = value
    with pytest.raises(ValueError, match=finding):
        bind_plic(tree, PlicSelection(PLIC, 1, 40, "sifive"))


def test_simulation_identity_and_aperture_count_refused(compile_tree: CompileTree) -> None:
    """Refuse a legacy layout on another platform and ambiguous register banks.

    Parameters
    ----------
    compile_tree
        Actual topology compiler and decoder.
    """
    tree = compile_tree(SOURCE.replace('"ucbbar,spike-bare"', '"other"'))
    with pytest.raises(ValueError, match="concrete register layout"):
        bind_plic(tree, PlicSelection(PLIC, 1, 1, "spike"))
    source = SOURCE.replace(
        "reg = <0 0xc000000 0 0x4000000>;", "reg = <0 0xc000000 0 0x4000000 0 0x10000000 0 0x100>; "
    )
    with pytest.raises(ValueError, match="one aligned"):
        bind_plic(compile_tree(source), PlicSelection(PLIC, 1, 1, "sifive"))


def test_incomplete_public_topology_refused(compile_tree: CompileTree) -> None:
    """Refuse an API input whose CPU node was removed after binary decoding.

    Parameters
    ----------
    compile_tree
        Original actual compiler and decoder.
    """
    tree = compile_tree(SOURCE)
    del tree.nodes[CPU]
    with pytest.raises(ValueError, match="not an original CPU"):
        bind_plic(tree, PlicSelection(PLIC, 1, 1, "sifive"))
