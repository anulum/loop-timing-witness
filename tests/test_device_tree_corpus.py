# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — device-tree reading corpus shared with the native analysis

"""Hold the Python device-tree readers' outcomes on real and changed blobs in a shared corpus.

Every tree starts from a source the real ``dtc`` compiled: the repository's
Spike platform, the small reservation and translation trees of the reader
tests, and changed copies of those sources that reach each refusal, branch
and bound of the readers. A few changed copies hold errors that ``dtc``
refuses at source level; they are compiled with ``-f``, as a careless or
hostile producer would, so the readers' own refusals are reached. Byte
changes then reach each header word, reservation entry, structure token and
string byte of the small tree, hand-built blobs reach each structure rule,
and synthetic blobs reach the reader's depth, node, path and size limits.

For each blob the corpus records what Python's ``decode_device_tree``
returns or the text it refuses with. For the compiled trees it also records
every node's register regions and cells, the phandle map and the dedicated
PLIC bindings. The native analysis reads the same corpus in its unit tests.

The corpus stays below the repository's file size limit without losing
exactness: changed trees are stored as byte deltas of their reference blob,
refusal texts once in a table, bulk trees as a SHA-256 digest of a defined
binary form (``_tree_digest``), and the readers' outcomes of a changed
platform as the difference from the reference platform's outcomes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from functools import partial
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from test_device_tree_blob import SOURCE as RESERVATION_SOURCE
from test_device_tree_resources import SOURCE as TRANSLATION_SOURCE

from loop_timing_witness.device_tree_blob import DeviceTree, decode_device_tree
from loop_timing_witness.device_tree_interrupts import PlicSelection, bind_plic
from loop_timing_witness.device_tree_properties import phandle_nodes, single_cell, string_list
from loop_timing_witness.device_tree_resources import register_regions
from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from collections.abc import Callable

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/device-tree-cases.json"
CELLS: Final = (
    "#address-cells",
    "#size-cells",
    "#interrupt-cells",
    "phandle",
    "linux,phandle",
    "interrupt-parent",
    "riscv,ndev",
)
HEADER_VALUES: Final = (0, 1, 3, 4, 8, 16, 17, 18, 39, 40, 41, 0xFFFFFFFF)
TOKEN_VALUES: Final = (0, 1, 2, 3, 4, 5, 9, 0xFFFFFFFF)
PLIC_HARTS: Final = (-1, 0, 1, 2, 4, 5)
PLIC_SOURCES: Final = (-1, 0, 1, 2, 31, 32, 1023, 1024)
BINDINGS: Final[tuple[Literal["sifive", "spike"], ...]] = ("sifive", "spike")
ABSENT_PLIC: Final = "/soc/plic@absent"
ABSENT_NODE: Final = "/absent"
PLATFORM: Final = "spike platform"
RESERVATIONS: Final = "reservations"
MAX_CONTEXTS: Final = 15872
CONTEXT_UNIT: Final = struct.pack(">II", 1, 0xFFFFFFFF)
PLIC_CONTEXTS: Final = "interrupts-extended = <0x01 0x0b 0x01 0x09 0x02 0x0b 0x02 0x09>;"
FORCED: Final = frozenset(
    {
        "phandle alias disagrees",
        "reserved phandle",
        "duplicate phandle",
        "zero phandle",
        "phandle not a scalar",
    }
)
BUSES: Final = """\
\tbuses {
\t\t#address-cells = <0x01>;
\t\t#size-cells = <0x01>;
\t\tranges;
\t\tedge@ffffff00 { reg = <0xffffff00 0x100>; };
\t\tbeyond@ffffff00 { reg = <0xffffff00 0x101>; };
\t\tinner {
\t\t\t#address-cells = <0x02>;
\t\t\t#size-cells = <0x01>;
\t\t\tranges = <0x01 0x00 0xffff0000 0x30000>;
\t\t\tfits@100000000 { reg = <0x01 0x00 0x10000>; };
\t\t\tspills@100010000 { reg = <0x01 0x10000 0x10001>; };
\t\t\toutside@100040000 { reg = <0x01 0x40000 0x10>; };
\t\t};
\t};
\tzero-cells {
\t\t#address-cells = <0x00>;
\t\t#size-cells = <0x01>;
\t\tranges;
\t\tbad@0 { reg = <0x04>; };
\t\tmid {
\t\t\t#address-cells = <0x01>;
\t\t\t#size-cells = <0x01>;
\t\t\tranges;
\t\t\tleaf@0 { reg = <0x00 0x04>; };
\t\t};
\t};
\tdefaults {
\t\tranges;
\t\tleaf@10 { reg = <0x00 0x10 0x20>; };
\t};
\tmalformed-cells {
\t\t#address-cells = <0x01 0x02>;
\t\tleaf { reg = <0x00>; };
\t};
\twide-sizes {
\t\t#address-cells = <0x01>;
\t\t#size-cells = <0x03>;
\t\tleaf { reg = <0x00 0x00 0x00 0x00>; };
\t};
\twords { reg = [00 00 00 00 40]; };
\tempty-reg { reg; };
\tshort-reg { reg = <0x00 0x40000000 0x00>; };
\tat-limit { reg = <0xffffffff 0xffffff00 0x00 0x100>; };
\tpast-limit { reg = <0xffffffff 0xffffff00 0x00 0x200>; };
\tlargest { reg = <0x00 0x00 0xffffffff 0xffffffff>; };
\tranges-twice {
\t\t#address-cells = <0x02>;
\t\t#size-cells = <0x02>;
\t\tranges = <0x00 0x00 0x00 0x00 0x01 0x00 0x00 0x00 0x00 0x00 0x01 0x00>;
\t\tleaf@0 { reg = <0x00 0x00 0x00 0x04>; };
\t};
\tranges-window {
\t\t#address-cells = <0x02>;
\t\t#size-cells = <0x02>;
\t\tranges = <0x00 0x1000 0x00 0x5000 0x00 0x1000>;
\t\tbelow@ffc { reg = <0x00 0xffc 0x00 0x08>; };
\t\tfirst@1000 { reg = <0x00 0x1000 0x00 0x04>; };
\t\twhole@1000 { reg = <0x00 0x1000 0x00 0x1000>; };
\t\tover@1000 { reg = <0x00 0x1000 0x00 0x1001>; };
\t\tlast@1ffc { reg = <0x00 0x1ffc 0x00 0x04>; };
\t\tafter@2000 { reg = <0x00 0x2000 0x00 0x04>; };
\t};
\tshifted {
\t\t#address-cells = <0x01>;
\t\t#size-cells = <0x01>;
\t\tranges = <0x00 0x01 0x00 0x1000>;
\t\tleaf@10 { reg = <0x10 0x04>; };
\t};
\tsizeless {
\t\t#address-cells = <0x01>;
\t\t#size-cells = <0x00>;
\t\tranges;
\t\tleaf@4 { reg = <0x04>; };
\t};
\ttop {
\t\t#address-cells = <0x02>;
\t\t#size-cells = <0x02>;
\t\tranges = <0x00 0x00 0xffffffff 0xffffffff 0x00 0x02>;
\t\tstart@0 { reg = <0x00 0x00 0x00 0x00>; };
\t\tend@1 { reg = <0x00 0x01 0x00 0x00>; };
\t\tpast@1 { reg = <0x00 0x01 0x00 0x01>; };
\t};
"""
ROOT_INTC: Final = """\
\tintc {
\t\tcompatible = "riscv,cpu-intc";
\t\t#interrupt-cells = <0x01>;
\t\tinterrupt-controller;
\t\tphandle = <0x09>;
\t};
"""
CPU_CELLS: Final = "#address-cells = <0x01>;\n\t\t#size-cells = <0x00>;"
FIRST_CPU: Final = "reg = <0x01>;\n\t\t\tstatus"
SECOND_CPU: Final = "reg = <0x02>;\n\t\t\tstatus"
SECOND_INTC: Final = (
    "#interrupt-cells = <0x01>;\n\t\t\t\tinterrupt-controller;\n"
    '\t\t\t\tcompatible = "riscv,cpu-intc";\n\t\t\t\tphandle = <0x02>;'
)
PLIC_MARKER: Final = (
    "#interrupt-cells = <0x01>;\n\t\t\tinterrupt-controller;\n\t\t\tphandle = <0x03>;"
)
PLIC_REG: Final = "reg = <0x00 0xc000000 0x00 0x1000000>;"
PLATFORM_CHANGES: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "legacy phandle alias": (("phandle = <0x03>;", "phandle = <0x03>; linux,phandle = <0x03>;"),),
    "phandle alias disagrees": (
        ("phandle = <0x03>;", "phandle = <0x03>; linux,phandle = <0x04>;"),
    ),
    "legacy alias only": (("phandle = <0x03>;", "linux,phandle = <0x03>;"),),
    "reserved phandle": (("phandle = <0x03>;", "phandle = <0xffffffff>;"),),
    "zero phandle": (("phandle = <0x03>;", "phandle = <0x00>;"),),
    "phandle not a scalar": (("phandle = <0x03>;", "phandle = <0x03 0x04>;"),),
    "duplicate phandle": (("phandle = <0x02>;", "phandle = <0x01>;"),),
    "empty string element": (('compatible = "riscv,plic0";', 'compatible = "riscv,plic0", "";'),),
    "string not ASCII": (('compatible = "riscv,plic0";', 'compatible = "riscv,pl\\xe9c0";'),),
    "unterminated string": (('compatible = "riscv,plic0";', "compatible = [72 69 73 63];"),),
    "three address cells": (
        ("#address-cells = <0x02>;\n\t#size-cells", "#address-cells = <0x03>;\n\t#size-cells"),
    ),
    "missing translation": (('simple-bus";\n\t\tranges;', 'simple-bus";'),),
    "ranges geometry": (('simple-bus";\n\t\tranges;', 'simple-bus";\n\t\tranges = <0 0 0 0 0>;'),),
    "sifive layout": (('compatible = "riscv,plic0";', 'compatible = "sifive,plic-1.0.0";'),),
    "spike model absent": (('model = "ucbbar,spike-bare";', 'model = "other";'),),
    "model removed": (('\tmodel = "ucbbar,spike-bare";\n', ""),),
    "few sources": (("riscv,ndev = <0x1f>;", "riscv,ndev = <0x01>;"),),
    "ndev at bound": (("riscv,ndev = <0x1f>;", "riscv,ndev = <0x3ff>;"),),
    "ndev beyond bound": (("riscv,ndev = <0x1f>;", "riscv,ndev = <0x400>;"),),
    "ndev absent": (("\n\t\t\triscv,ndev = <0x1f>;", ""),),
    "small aperture": ((PLIC_REG, "reg = <0x00 0xc000000 0x00 0x2000>;"),),
    "tight aperture": ((PLIC_REG, "reg = <0x00 0xc000000 0x00 0x200008>;"),),
    "aperture one byte short": ((PLIC_REG, "reg = <0x00 0xc000000 0x00 0x200007>;"),),
    "unaligned aperture": ((PLIC_REG, "reg = <0x00 0xc000002 0x00 0x1000000>;"),),
    "zero aperture": ((PLIC_REG, "reg = <0x00 0x00 0x00 0x1000000>;"),),
    "two apertures": (
        (PLIC_REG, "reg = <0x00 0xc000000 0x00 0x1000000 0x00 0xe000000 0x00 0x1000>;"),
    ),
    "not a controller": (("interrupt-controller;\n\t\t\tphandle = <0x03>;", "phandle = <0x03>;"),),
    "plic marker with a value": (
        (
            "interrupt-controller;\n\t\t\tphandle = <0x03>;",
            "interrupt-controller = <0x01>;\n\t\t\tphandle = <0x03>;",
        ),
    ),
    "plic cells absent": (
        (PLIC_MARKER, PLIC_MARKER.removeprefix("#interrupt-cells = <0x01>;\n\t\t\t")),
    ),
    "plic cells two": ((PLIC_MARKER, PLIC_MARKER.replace("<0x01>", "<0x02>")),),
    "unsupported cpu interrupt": (("0x01 0x0b 0x01 0x09", "0x01 0x0b 0x01 0x05"),),
    "two machine contexts": (("0x01 0x0b 0x01 0x09", "0x01 0x0b 0x01 0x0b"),),
    "undeclared context phandle": (("0x01 0x0b 0x01 0x09", "0x09 0x0b 0x01 0x09"),),
    "odd context cells": (("0x02 0x0b 0x02 0x09>", "0x02 0x0b 0x02>"),),
    "root intc": (
        ("\n\thtif {", "\n" + ROOT_INTC + "\n\thtif {"),
        ("0x01 0x0b 0x01 0x09", "0x09 0x0b 0x01 0x09"),
    ),
    "cpu type wrong": (
        ('device_type = "cpu";\n\t\t\treg = <0x02>;', 'device_type = "cpux";\n\t\t\treg = <0x02>;'),
    ),
    "cpu type absent": (('device_type = "cpu";\n\t\t\treg = <0x02>;', "reg = <0x02>;"),),
    "intc not riscv": (
        (
            'compatible = "riscv,cpu-intc";\n\t\t\t\tphandle = <0x02>',
            'compatible = "other";\n\t\t\t\tphandle = <0x02>',
        ),
    ),
    "intc cells two": ((SECOND_INTC, SECOND_INTC.replace("<0x01>", "<0x02>")),),
    "intc not a controller": (
        (SECOND_INTC, SECOND_INTC.replace("interrupt-controller;\n\t\t\t\t", "")),
    ),
    "intc marker with a value": (
        (
            SECOND_INTC,
            SECOND_INTC.replace("interrupt-controller;", "interrupt-controller = <0x01>;"),
        ),
    ),
    "cpu identifier geometry": ((SECOND_CPU, "reg = <0x00 0x02>;\n\t\t\tstatus"),),
    "cpus cells absent": ((CPU_CELLS, "#size-cells = <0x00>;"),),
    "cpus size cells": ((CPU_CELLS, CPU_CELLS.replace("<0x00>", "<0x01>")),),
    "cpus three cells": (
        (CPU_CELLS, CPU_CELLS.replace("<0x01>", "<0x03>")),
        (FIRST_CPU, "reg = <0x00 0x00 0x01>;\n\t\t\tstatus"),
        (SECOND_CPU, "reg = <0x00 0x00 0x02>;\n\t\t\tstatus"),
    ),
    "two-cell cpu identifiers": (
        (CPU_CELLS, CPU_CELLS.replace("<0x01>", "<0x02>")),
        (FIRST_CPU, "reg = <0x00 0x01>;\n\t\t\tstatus"),
        (SECOND_CPU, "reg = <0x00 0x02>;\n\t\t\tstatus"),
    ),
    "wide cpu identifier": (
        (CPU_CELLS, CPU_CELLS.replace("<0x01>", "<0x02>")),
        (FIRST_CPU, "reg = <0x00 0x01>;\n\t\t\tstatus"),
        (SECOND_CPU, "reg = <0x01 0x02>;\n\t\t\tstatus"),
    ),
    "same cpu twice": ((SECOND_CPU, "reg = <0x01>;\n\t\t\tstatus"),),
    "cpus size cells absent": ((CPU_CELLS, "#address-cells = <0x01>;"),),
    "contexts absent": (("\n\t\t\t" + PLIC_CONTEXTS, ""),),
    "context without compatible": (
        (
            'bootargs = "console=ttyS0 earlycon";',
            'bootargs = "console=ttyS0 earlycon";\n\t\tphandle = <0x0a>;',
        ),
        ("0x01 0x0b 0x01 0x09", "0x0a 0x0b 0x01 0x09"),
    ),
    "assorted buses": (("\n\thtif {", "\n" + BUSES + "\n\thtif {"),),
    "contexts at the bound": (
        (
            PLIC_CONTEXTS,
            "interrupts-extended = <0x01 0x0b" + " 0x01 0xffffffff" * (MAX_CONTEXTS - 1) + ">;",
        ),
    ),
    "contexts beyond the bound": (
        (
            PLIC_CONTEXTS,
            "interrupts-extended = <0x01 0x0b" + " 0x01 0xffffffff" * MAX_CONTEXTS + ">;",
        ),
    ),
}
RUNS: Final = {"contexts at the bound": MAX_CONTEXTS - 1, "contexts beyond the bound": MAX_CONTEXTS}
RESERVATION_CHANGES: Final = {
    "adjacent reservations": "/memreserve/ 0x80010000 0x10000;\n/memreserve/ 0x80020000 0x1000;",
    "unsorted reservations": "/memreserve/ 0x80030000 0x1000;\n/memreserve/ 0x80010000 0x10000;",
    "overlapping reservations": "/memreserve/ 0x80010000 0x10000;\n/memreserve/ 0x80018000 0x1000;",
}
BEGIN: Final = struct.pack(">I", 1)
END_NODE: Final = struct.pack(">I", 2)
NOP: Final = struct.pack(">I", 4)
END: Final = struct.pack(">I", 9)
ROOT: Final = BEGIN + bytes(4)


def _platform() -> str:
    """Return the repository's Spike platform source.

    Returns
    -------
    str
        Complete DTS text.
    """
    return (REPOSITORY_ROOT / "tests/platforms/spike_multihart.dts").read_text(encoding="utf-8")


def _changed(source: str, changes: tuple[tuple[str, str], ...], name: str) -> str:
    """Apply text replacements that each match the source exactly once.

    Parameters
    ----------
    source
        Complete DTS text.
    changes
        ``(old, new)`` replacements, applied in order.
    name
        Case name for the failure message.

    Returns
    -------
    str
        Changed DTS text.
    """
    for old, new in changes:
        assert source.count(old) == 1, f"{name}: {old!r}"
        source = source.replace(old, new)
    return source


def _compile(source: str, directory: Path, *, force: bool) -> bytes:
    """Compile one DTS text with the real ``dtc``.

    A forced compilation must be one that ``dtc`` refuses without ``-f``.

    Parameters
    ----------
    source
        Complete DTS text.
    directory
        Owned directory for the source and the blob.
    force
        Whether ``dtc`` must write the blob despite its own source checks.

    Returns
    -------
    bytes
        Compiled blob.
    """
    compiler = shutil.which("dtc")
    assert compiler is not None, "dtc is required for the device-tree corpus"
    text, blob = directory / "tree.dts", directory / "tree.dtb"
    text.write_text(source, encoding="utf-8")
    command = [compiler, "-q", "-I", "dts", "-O", "dtb", "-o", str(blob), str(text)]
    plain = subprocess.run(command, capture_output=True, check=False, timeout=scaled(60))
    if not force:
        assert plain.returncode == 0, plain.stderr.decode(errors="replace")
        return blob.read_bytes()
    assert plain.returncode != 0, "a forced source must be one that dtc refuses"
    subprocess.run(
        [*command[:2], "-f", *command[2:]], capture_output=True, check=True, timeout=scaled(60)
    )
    return blob.read_bytes()


def _blob(
    structure: bytes,
    strings: bytes = b"",
    *,
    reservations: bytes = bytes(16),
    reservations_last: bool = False,
    strings_first: bool = False,
) -> bytes:
    """Assemble a version 17 blob from its blocks.

    Parameters
    ----------
    structure
        Complete structure block.
    strings
        Complete strings block.
    reservations
        Complete reservation map, terminator included.
    reservations_last
        Whether the map follows the other blocks instead of the header.
    strings_first
        Whether the strings block precedes the structure block.

    Returns
    -------
    bytes
        Blob with a consistent header.
    """
    if reservations_last:
        structure_offset = 40
        strings_offset = structure_offset + len(structure)
        padding = -(strings_offset + len(strings)) % 8
        reserved = strings_offset + len(strings) + padding
        body = structure + strings + bytes(padding) + reservations
    elif strings_first:
        reserved = 40
        strings_offset = reserved + len(reservations)
        structure_offset = strings_offset + len(strings) + (-len(strings) % 4)
        body = reservations + strings + bytes(-len(strings) % 4) + structure
    else:
        reserved = 40
        structure_offset = reserved + len(reservations)
        strings_offset = structure_offset + len(structure)
        body = reservations + structure + strings
    header = struct.pack(
        ">10I",
        0xD00DFEED,
        40 + len(body),
        structure_offset,
        strings_offset,
        reserved,
        17,
        16,
        0,
        len(strings),
        len(structure),
    )
    return header + body


def _node(name: bytes, body: bytes = b"") -> bytes:
    """Return one structure-block node with its name padded to a word.

    Parameters
    ----------
    name
        Node name without the terminator.
    body
        Properties and children.

    Returns
    -------
    bytes
        Begin token, padded name, body and end token.
    """
    text = name + b"\0"
    text += bytes(-len(text) % 4)
    return BEGIN + text + body + END_NODE


def _property(name_offset: int, value: bytes = b"") -> bytes:
    """Return one structure-block property with its value padded to a word.

    Parameters
    ----------
    name_offset
        Offset of the name in the strings block.
    value
        Property bytes.

    Returns
    -------
    bytes
        Property token, header, value and padding.
    """
    header = struct.pack(">III", 3, len(value), name_offset)
    return header + value + bytes(-len(value) % 4)


def _structures() -> dict[str, bytes]:
    """Return hand-built blobs that reach each structure and reservation-map rule.

    Returns
    -------
    dict[str, bytes]
        Blob by case name.
    """
    names = b"reg\0compatible\0"
    # A whole number of words: the next block can start exactly where this one ends.
    words = names + b"\0"
    at_map = bytearray(_blob(ROOT + END_NODE + END))
    at_map[12:16] = struct.pack(">I", 40)
    child = _node(b"a")
    entry = struct.pack(">QQ", 0x80000000, 0x1000)
    value = struct.pack(">III", 3, 1, 0) + b"\x01\x01\0\0"
    return {
        "smallest tree": _blob(ROOT + END_NODE + END),
        "nops around the tree": _blob(NOP + ROOT + NOP + END_NODE + NOP + END),
        "duplicate node path": _blob(ROOT + child + child + END_NODE + END),
        "second root": _blob(ROOT + END_NODE + ROOT + END_NODE + END),
        "named root": _blob(_node(b"r") + END),
        "empty child name": _blob(ROOT + _node(b"") + END_NODE + END),
        "slash in child name": _blob(ROOT + _node(b"a/b") + END_NODE + END),
        "child name not ASCII": _blob(ROOT + BEGIN + b"\x80\0\0\0" + END_NODE + END_NODE + END),
        "child name padding not zero": _blob(
            ROOT + BEGIN + b"a\0\x01\0" + END_NODE + END_NODE + END
        ),
        "unterminated child name": _blob(ROOT + BEGIN + b"abcd"),
        "child name at the block end": _blob(ROOT + BEGIN),
        "property before the root": _blob(_property(0) + ROOT + END_NODE + END, names),
        "property after the root": _blob(ROOT + END_NODE + _property(0) + END, names),
        "property after a child": _blob(ROOT + child + _property(0) + END_NODE + END, names),
        "property in a child": _blob(
            ROOT + _node(b"a", _property(4, b"x\0")) + END_NODE + END, names
        ),
        "empty property name": _blob(ROOT + _property(3) + END_NODE + END, names),
        "slash in property name": _blob(ROOT + _property(0) + END_NODE + END, b"a/b\0"),
        "property name not ASCII": _blob(ROOT + _property(0) + END_NODE + END, b"\x80\0"),
        "unterminated property name": _blob(ROOT + _property(0) + END_NODE + END, b"reg"),
        "property name offset at the block end": _blob(
            ROOT + _property(len(names)) + END_NODE + END, names
        ),
        "duplicate property": _blob(ROOT + _property(0) + _property(0) + END_NODE + END, names),
        "property value padding not zero": _blob(ROOT + value + END_NODE + END, names),
        "property value fills the block": _blob(
            ROOT + struct.pack(">III", 3, 4, 0) + b"abcd", names
        ),
        "property value past the block": _blob(
            ROOT + struct.pack(">III", 3, 5, 0) + b"abcd", names
        ),
        "property header fills the block": _blob(ROOT + struct.pack(">III", 3, 0, 0), names),
        "truncated property header": _blob(ROOT + struct.pack(">II", 3, 0), names),
        "unmatched end": _blob(END_NODE + END),
        "end inside a node": _blob(ROOT + END),
        "end before any node": _blob(END),
        "nops only": _blob(NOP + NOP + END),
        "data after the end": _blob(ROOT + END_NODE + END + NOP),
        "unknown token": _blob(ROOT + struct.pack(">I", 5) + END_NODE + END),
        "no end token": _blob(ROOT + END_NODE),
        "reservations last": _blob(
            ROOT + END_NODE + END, words, reservations=entry + bytes(16), reservations_last=True
        ),
        "strings before the structure": _blob(
            ROOT + _property(4, b"x\0") + END_NODE + END, words, strings_first=True
        ),
        "empty strings block at the reservation map": bytes(at_map),
        "reservations last without terminator": _blob(
            ROOT + END_NODE + END, names, reservations=entry, reservations_last=True
        ),
    }


def _limits() -> tuple[dict[str, bytes], dict[str, list[list[Any]]]]:
    """Return blobs at and beyond the reader's depth, node, path and size limits.

    Each blob is a list of ``[hex, repeat]`` or ``[{"chunk": name}, repeat]``
    segments, so the corpus stays small.

    Returns
    -------
    tuple[dict[str, bytes], dict[str, list[list[Any]]]]
        Shared chunks, and segments by case name.
    """
    cases: dict[str, list[list[Any]]] = {}
    nested = BEGIN + b"a\0\0\0"
    for depth in (64, 65):
        structure = ROOT + nested * (depth - 1) + END_NODE * depth + END
        head, tail = _blob(structure).split(nested * (depth - 1))
        cases[f"depth {depth}"] = [[head.hex(), 1], [nested.hex(), depth - 1], [tail.hex(), 1]]
    children = b"".join(_node(f"c{index:03d}".encode()) for index in range(128))
    chunks = {"children": children}
    for count, extra in ((16384, b""), (16385, _node(b"c128"))):
        parents = [_node(f"p{index:03d}".encode(), children) for index in range(127)]
        parents[-1] = parents[-1][:-4] + extra + END_NODE
        blob = _blob(ROOT + b"".join(parents) + END_NODE + END)
        segments: list[list[Any]] = [[blob[: 40 + 16 + len(ROOT)].hex(), 1]]
        for index in range(127):
            segments.append([(BEGIN + f"p{index:03d}".encode() + b"\0\0\0\0").hex(), 1])
            segments.append([{"chunk": "children"}, 1])
            segments.append([(extra if index == 126 else b"").hex() + END_NODE.hex(), 1])
        segments.append([(END_NODE + END).hex(), 1])
        assert _joined(segments, chunks) == blob
        cases[f"nodes {count}"] = segments
    for length in (4096, 4097):
        structure = ROOT + _node(b"p" * (length - 1)) + END_NODE + END
        head, tail = _blob(structure).split(b"p" * (length - 1))
        cases[f"path {length}"] = [[head.hex(), 1], ["70", length - 1], [tail.hex(), 1]]
    for size in (16 * 1024 * 1024, 16 * 1024 * 1024 + 1):
        strings = bytes(size % 4)
        nops = (size - 40 - 16 - len(ROOT) - 8 - len(strings)) // 4
        blob = _blob(ROOT + NOP * nops + END_NODE + END, strings)
        assert len(blob) == size
        head = blob[: 40 + 16 + len(ROOT)]
        tail = blob[len(head) + 4 * nops :]
        cases[f"size {size}"] = [[head.hex(), 1], [NOP.hex(), nops], [tail.hex(), 1]]
    return chunks, cases


def _header_values(base: bytes) -> dict[int, list[int]]:
    """Return each header word's replacement values, with bounds around the original layout.

    Parameters
    ----------
    base
        Compiled small tree.

    Returns
    -------
    dict[int, list[int]]
        Sorted 32-bit values by header word index.
    """
    words = struct.unpack_from(">10I", base)
    total = len(base)
    values = {
        index: {*HEADER_VALUES, *(word + step for step in (-8, -4, -1, 1, 4, 8))}
        for index, word in enumerate(words)
    }
    values[2] |= {total - words[9], total - words[9] + 4}
    values[3] |= {total - words[8], total - words[8] + 1}
    aligned_end = total + (-total % 8)
    values[4] |= {total - 16, total - 8, total, aligned_end, aligned_end + 8}
    values[8] |= {total - words[3], total - words[3] + 1}
    values[9] |= {total - words[2], total - words[2] + 4}
    return {
        index: sorted(value for value in found if 0 <= value <= 0xFFFFFFFF)
        for index, found in values.items()
    }


def _small_changes(base: bytes) -> dict[str, list[list[Any]]]:
    """Return byte changes of the small reservation tree, each one ``[offset, hex]`` edit.

    The names keep the changes distinct; the corpus stores only the edits.

    Parameters
    ----------
    base
        Compiled small tree.

    Returns
    -------
    dict[str, list[list[Any]]]
        Edits by case name.
    """
    edits: dict[str, list[list[Any]]] = {}
    for index, values in _header_values(base).items():
        for value in values:
            edits[f"header word {index} = {value}"] = [[index * 4, struct.pack(">I", value).hex()]]
    structure, structure_size = (
        struct.unpack_from(">I", base, 8)[0],
        struct.unpack_from(">I", base, 36)[0],
    )
    for offset in range(structure, structure + structure_size, 4):
        for value in TOKEN_VALUES:
            edits[f"structure word {offset} = {value}"] = [[offset, struct.pack(">I", value).hex()]]
    strings, string_size = (
        struct.unpack_from(">I", base, 12)[0],
        struct.unpack_from(">I", base, 32)[0],
    )
    for offset in range(strings, strings + string_size):
        for value in (0x00, 0x2F, 0x80):
            edits[f"string byte {offset} = {value}"] = [[offset, f"{value:02x}"]]
    reserved = struct.unpack_from(">I", base, 16)[0]
    for name, entry in {
        "reservation size zero": struct.pack(">QQ", 0x80010000, 0),
        "reservation at address zero": struct.pack(">QQ", 0, 0x1000),
        "reservation ends at the address limit": struct.pack(">QQ", 0xFFFFFFFFFFFF0000, 0x10000),
        "reservation beyond the address space": struct.pack(">QQ", 0xFFFFFFFFFFFF0000, 0x20000),
    }.items():
        edits[name] = [[reserved, entry.hex()]]
    terminator = struct.pack(">QQ", 0x80030000, 0x1000).hex()
    edits["reservation terminator replaced"] = [[reserved + 16, terminator]]
    return edits


def _attempt(call: Callable[[], object]) -> dict[str, object]:
    """Return a reader's value, or the text it refuses with.

    Parameters
    ----------
    call
        Reader call.

    Returns
    -------
    dict[str, object]
        ``{"value": ...}`` or ``{"refusal": text}``.
    """
    try:
        return {"value": call()}
    except ValueError as error:
        return {"refusal": str(error)}


def _tree(tree: DeviceTree) -> dict[str, Any]:
    """Return a decoded tree as plain data in document order.

    Parameters
    ----------
    tree
        Decoded tree.

    Returns
    -------
    dict[str, Any]
        Nodes with their properties as hexadecimal bytes, reservations and boot CPU.
    """
    return {
        "nodes": [
            [node.path, [[name, value.hex()] for name, value in node.properties.items()]]
            for node in tree.nodes.values()
        ],
        "reservations": [list(entry) for entry in tree.reservations],
        "boot_cpu": tree.boot_cpu,
    }


def _tree_digest(tree: DeviceTree) -> str:
    """Return the SHA-256 of a decoded tree's defined binary form.

    The form is the boot CPU and the reservation count as big-endian 32-bit
    words, each reservation as two big-endian 64-bit words, the node count as
    a word, and per node in document order its ASCII path and property
    count, then each property's ASCII name and exact value. Every path, name
    and value is preceded by its length as a word.

    Parameters
    ----------
    tree
        Decoded tree.

    Returns
    -------
    str
        Lowercase hexadecimal digest.
    """
    digest = hashlib.sha256(struct.pack(">II", tree.boot_cpu, len(tree.reservations)))
    for address, size in tree.reservations:
        digest.update(struct.pack(">QQ", address, size))
    digest.update(struct.pack(">I", len(tree.nodes)))
    for node in tree.nodes.values():
        path = node.path.encode("ascii")
        digest.update(struct.pack(">I", len(path)) + path + struct.pack(">I", len(node.properties)))
        for name, value in node.properties.items():
            raw = name.encode("ascii")
            digest.update(struct.pack(">I", len(raw)) + raw + struct.pack(">I", len(value)) + value)
    return digest.hexdigest()


def _regions(tree: DeviceTree, path: str) -> list[list[int]]:
    """Return one node's translated register regions as plain pairs.

    Parameters
    ----------
    tree
        Decoded tree.
    path
        Node path.

    Returns
    -------
    list[list[int]]
        ``[address, size]`` pairs.
    """
    return [[region.address, region.size] for region in register_regions(tree, path)]


def _strings(tree: DeviceTree, path: str) -> list[str]:
    """Return one node's ``compatible`` strings.

    Parameters
    ----------
    tree
        Decoded tree.
    path
        Node path.

    Returns
    -------
    list[str]
        Strings in order.
    """
    return list(string_list(tree.nodes[path], "compatible"))


def _cell(tree: DeviceTree, path: str, name: str) -> int:
    """Return one node's single-cell property.

    Parameters
    ----------
    tree
        Decoded tree.
    path
        Node path.
    name
        Property name.

    Returns
    -------
    int
        The cell.
    """
    return single_cell(tree.nodes[path], name)


def _phandles(tree: DeviceTree) -> dict[str, str]:
    """Return the phandle map as handle text to node path.

    Parameters
    ----------
    tree
        Decoded tree.

    Returns
    -------
    dict[str, str]
        Node path by decimal handle.
    """
    return {str(handle): node.path for handle, node in phandle_nodes(tree).items()}


def _plic(tree: DeviceTree, selection: PlicSelection) -> list[int]:
    """Return one PLIC binding's context and register addresses.

    Parameters
    ----------
    tree
        Decoded tree.
    selection
        Dedicated hart, source and layout.

    Returns
    -------
    list[int]
        Context, priority, enable word, threshold and claim addresses.
    """
    registers = bind_plic(tree, selection)
    return [
        registers.context,
        registers.priority,
        registers.enable_word,
        registers.threshold,
        registers.claim,
    ]


def _readers(tree: DeviceTree) -> dict[str, dict[str, object]]:
    """Return every reader outcome of one tree under a flat key.

    Keys are ``regions <path>``, ``compatible <path>``, ``<cell name>
    <path>``, ``phandles`` and ``plic <path> <binding> <hart> <source>``; an
    absent node path and an absent PLIC path are asked once each.

    Parameters
    ----------
    tree
        Decoded tree.

    Returns
    -------
    dict[str, dict[str, object]]
        Reader outcome by key.
    """
    outcomes = {}
    for path, node in tree.nodes.items():
        outcomes[f"regions {path}"] = _attempt(partial(_regions, tree, path))
        if "compatible" in node.properties:
            outcomes[f"compatible {path}"] = _attempt(partial(_strings, tree, path))
        for name in CELLS:
            if name in node.properties:
                outcomes[f"{name} {path}"] = _attempt(partial(_cell, tree, path, name))
    outcomes[f"regions {ABSENT_NODE}"] = _attempt(partial(_regions, tree, ABSENT_NODE))
    outcomes["phandles"] = _attempt(partial(_phandles, tree))
    for path in (path for path in tree.nodes if "plic" in path):
        for binding in BINDINGS:
            for hart in PLIC_HARTS:
                for source in PLIC_SOURCES:
                    selection = PlicSelection(path, hart, source, binding)
                    outcomes[f"plic {path} {binding} {hart} {source}"] = _attempt(
                        partial(_plic, tree, selection)
                    )
    absent = PlicSelection(ABSENT_PLIC, 1, 1, "spike")
    outcomes[f"plic {ABSENT_PLIC} spike 1 1"] = _attempt(partial(_plic, tree, absent))
    return outcomes


def _outcome(blob: bytes, *, full_tree: bool) -> tuple[dict[str, Any], DeviceTree | None]:
    """Return the decode outcome of one blob and the decoded tree.

    Parameters
    ----------
    blob
        Complete blob.
    full_tree
        Whether to record the whole tree instead of its digest.

    Returns
    -------
    tuple[dict[str, Any], DeviceTree | None]
        ``{"tree": ...}``, ``{"tree_sha256": ...}`` or ``{"refusal": text}``, and the tree.
    """
    try:
        tree = decode_device_tree(blob)
    except ValueError as error:
        return {"refusal": str(error)}, None
    if full_tree:
        return {"tree": _tree(tree)}, tree
    return {"tree_sha256": _tree_digest(tree)}, tree


def _apply(base: bytes, edits: list[list[Any]]) -> bytes:
    """Apply ``[offset, hex]`` edits to a copy of a base blob.

    Parameters
    ----------
    base
        Original blob.
    edits
        Byte replacements.

    Returns
    -------
    bytes
        Changed copy.
    """
    blob = bytearray(base)
    for offset, text in edits:
        data = bytes.fromhex(text)
        blob[offset : offset + len(data)] = data
    return bytes(blob)


def _joined(segments: list[list[Any]], chunks: dict[str, bytes]) -> bytes:
    """Concatenate ``[hex, repeat]`` and ``[{"chunk": name, ...}, repeat]`` segments.

    A chunk part may carry ``start`` and ``end`` to take a slice of the chunk.

    Parameters
    ----------
    segments
        Corpus segments.
    chunks
        Shared chunks by name.

    Returns
    -------
    bytes
        Blob.
    """
    parts = []
    for part, count in segments:
        if isinstance(part, str):
            parts.append(bytes.fromhex(part) * count)
        else:
            chunk = chunks[part["chunk"]]
            parts.append(chunk[part.get("start", 0) : part.get("end", len(chunk))] * count)
    return b"".join(parts)


def _blocks(blob: bytes) -> list[int]:
    """Return a compiled blob's block boundaries.

    Parameters
    ----------
    blob
        Compiled blob.

    Returns
    -------
    list[int]
        Sorted offsets of the header end and each block's start and end.
    """
    words = struct.unpack_from(">10I", blob)
    edges = {0, 40, words[4], words[2], words[2] + words[9], words[3], words[3] + words[8]}
    return sorted({*edges, len(blob)})


def _delta(reference: str, base: bytes, blob: bytes, run: int) -> list[list[Any]]:
    """Return a compiled blob as segments that copy unchanged runs of its reference.

    Per block, the common prefix and suffix with the reference's block are
    copied and the rest is literal. A literal holding ``run`` repeated
    context words is stored as one repeated segment.

    Parameters
    ----------
    reference
        Reference chunk name.
    base
        Reference blob.
    blob
        Changed blob with the same block order.
    run
        Repeat count of the context word to fold, or zero.

    Returns
    -------
    list[list[Any]]
        Segments that rebuild the blob.
    """
    segments: list[list[Any]] = []
    old, new = _blocks(base), _blocks(blob)
    assert len(old) == len(new)
    for (start, end), (first, last) in zip(pairwise(old), pairwise(new), strict=True):
        before, after = base[start:end], blob[first:last]
        shorter = min(len(before), len(after))
        prefix = 0
        while prefix < shorter and before[prefix] == after[prefix]:
            prefix += 1
        suffix = 0
        while suffix < shorter - prefix and before[-1 - suffix] == after[-1 - suffix]:
            suffix += 1
        if prefix:
            segments.append([{"chunk": reference, "start": start, "end": start + prefix}, 1])
        literal = after[prefix : len(after) - suffix]
        if run and CONTEXT_UNIT * run in literal:
            head, tail = literal.split(CONTEXT_UNIT * run)
            segments += [[head.hex(), 1], [CONTEXT_UNIT.hex(), run], [tail.hex(), 1]]
        elif literal:
            segments.append([literal.hex(), 1])
        if suffix:
            segments.append([{"chunk": reference, "start": end - suffix, "end": end}, 1])
    assert _joined(segments, {reference: base}) == blob
    return segments


def _changes(reference: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return reader outcomes that differ from a reference tree's outcomes.

    Parameters
    ----------
    reference
        Reference outcomes by key.
    current
        Outcomes by key.

    Returns
    -------
    dict[str, Any]
        Changed or added outcomes under ``set`` and removed keys under ``drop``.
    """
    return {
        "set": {key: value for key, value in current.items() if reference.get(key) != value},
        "drop": sorted(key for key in reference if key not in current),
    }


def _refusals(value: object) -> set[str]:
    """Return every refusal text held in a corpus value.

    Parameters
    ----------
    value
        Corpus value.

    Returns
    -------
    set[str]
        Refusal texts.
    """
    if isinstance(value, dict):
        found = {value["refusal"]} if isinstance(value.get("refusal"), str) else set()
        return found.union(*(_refusals(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_refusals(item) for item in value))
    return set()


def _indexed(value: object, texts: dict[str, int]) -> object:
    """Replace every refusal text by its index in the sorted text table.

    Parameters
    ----------
    value
        Corpus value.
    texts
        Index by refusal text.

    Returns
    -------
    object
        Value with integer refusals.
    """
    if isinstance(value, dict):
        return {
            key: texts[item] if key == "refusal" else _indexed(item, texts)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_indexed(item, texts) for item in value]
    return value


def corpus(directory: Path) -> dict[str, Any]:
    """Build the complete corpus from real ``dtc`` output and Python's readers.

    Parameters
    ----------
    directory
        Owned empty directory for the compiler runs.

    Returns
    -------
    dict[str, Any]
        Text table, shared chunks and cases.
    """
    platform = _platform()
    primary = {
        PLATFORM: _compile(platform, directory, force=False),
        RESERVATIONS: _compile(RESERVATION_SOURCE, directory, force=False),
        "translation": _compile(TRANSLATION_SOURCE, directory, force=False),
    }
    limit_chunks, limits = _limits()
    chunks = {**primary, **limit_chunks}
    cases: list[dict[str, Any]] = []
    readers: dict[str, dict[str, Any]] = {}
    for name, blob in primary.items():
        outcome, tree = _outcome(blob, full_tree=True)
        assert tree is not None
        readers[name] = _readers(tree)
        cases.append({"name": name, "blob": {"chunk": name}, **outcome, "readers": readers[name]})
    for name, line in RESERVATION_CHANGES.items():
        source = _changed(RESERVATION_SOURCE, (("/memreserve/ 0x80010000 0x10000;", line),), name)
        blob = _compile(source, directory, force=False)
        outcome, tree = _outcome(blob, full_tree=True)
        segments = _delta(RESERVATIONS, primary[RESERVATIONS], blob, 0)
        case = {"name": name, "blob": {"segments": segments}, **outcome}
        if tree is not None:
            case["readers"] = _readers(tree)
        cases.append(case)
    for name, changes in PLATFORM_CHANGES.items():
        blob = _compile(_changed(platform, changes, name), directory, force=name in FORCED)
        outcome, tree = _outcome(blob, full_tree=False)
        assert tree is not None, name
        segments = _delta(PLATFORM, primary[PLATFORM], blob, RUNS.get(name, 0))
        changed = {"from": PLATFORM, **_changes(readers[PLATFORM], _readers(tree))}
        cases.append(
            {"name": name, "blob": {"segments": segments}, **outcome, "readers_change": changed}
        )
    for name, blob in _structures().items():
        outcome, _ = _outcome(blob, full_tree=True)
        cases.append({"name": name, "blob": {"segments": [[blob.hex(), 1]]}, **outcome})
    small = primary[RESERVATIONS]
    sweep = []
    for edits in _small_changes(small).values():
        outcome, _ = _outcome(_apply(small, edits), full_tree=False)
        sweep.append([*edits[0], outcome])
    for length in (0, 39, 40, len(small) - 1):
        outcome, _ = _outcome(small[:length], full_tree=False)
        blob_spec = {"chunk": RESERVATIONS, "length": length}
        cases.append({"name": f"truncated to {length}", "blob": blob_spec, **outcome})
    for name, segments in limits.items():
        outcome, _ = _outcome(_joined(segments, chunks), full_tree=False)
        cases.append({"name": name, "blob": {"segments": segments}, **outcome})
    assert len({case["name"] for case in cases}) == len(cases)
    texts = sorted(_refusals([cases, sweep]))
    index = {text: number for number, text in enumerate(texts)}
    return {
        "schema": "loop-timing-witness.device-tree-cases.v1",
        "description": (
            "Python device-tree readers' outcomes. A case's blob is a named chunk, a chunk "
            "cut to length, or the concatenation of [hex, repeat] and [{chunk, start?, end?}, "
            "repeat] segments. Each sweep row is one [offset, hex] change of the reservations "
            "chunk and its outcome. A refusal is an index into texts. "
            "tree_sha256 hashes the tree's binary form: boot CPU and reservation count as "
            "big-endian 32-bit words, each reservation as two 64-bit words, the node count, "
            "then per node its path and property count and per property its name and value, "
            "each path, name and value preceded by its 32-bit length. readers_change holds "
            "the outcomes that differ from the named case's readers."
        ),
        "texts": texts,
        "chunks": {name: blob.hex() for name, blob in chunks.items()},
        "cases": _indexed(cases, index),
        "sweep": _indexed(sweep, index),
    }


def _text(document: dict[str, Any]) -> str:
    """Return the committed text form of the corpus.

    Parameters
    ----------
    document
        Corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_outcomes(tmp_path: Path) -> None:
    """Rebuild the corpus from dtc and the Python readers and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the compiler runs.
    """
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
