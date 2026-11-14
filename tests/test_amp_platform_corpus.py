# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP platform binding corpus shared with the native analysis

"""Hold Python's AMP platform binding in a shared corpus.

Every case compiles the repository's Spike platform (``tests/platforms/
spike_multihart.dts``), changed as the case names, with the real ``dtc`` and
binds it with ``bind_platform`` under the selection the ISA image uses, or a
changed one. The cases break each rule of the reservations, the backing RAM,
the Witness device, its interrupt and aperture, the other interrupt
consumers and register extents, and the PLIC aperture, and keep the forms
Python admits.

The committed form keeps the base blob once; a case's blob is the base with
byte ranges replaced (``[start, end, hex]`` in base order). An outcome is the
admitted platform as ``dataclasses.asdict`` writes it, or Python's refusal
text.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Final

from test_device_tree_corpus import _changed, _compile, _platform

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_memory import MemorySelection
from loop_timing_witness.amp_platform import bind_platform
from loop_timing_witness.device_tree_blob import decode_device_tree
from loop_timing_witness.device_tree_interrupts import PlicSelection

if TYPE_CHECKING:
    from pathlib import Path

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-platform-cases.json"
SELECTION: Final = {
    "ram": "/memory@80000000",
    "firmware": "/reserved-memory/firmware@80000000",
    "shared": "/reserved-memory/telemetry@80080000",
    "mailbox": 16496,
    "stack": 16384,
    "device": "/witness@40000000",
    "plic": "/soc/plic@c000000",
    "hart": 2,
    "source": 2,
    "layout": "spike",
}
WITNESS: Final = "reg = <0 0x40000000 0 256>; interrupt-parent = <3>; interrupts = <2>;"
FIRMWARE: Final = "firmware@80000000 { reg = <0 0x80000000 0 0x80000>; no-map; };"
TELEMETRY: Final = "telemetry@80080000 { reg = <0 0x80080000 0 0x10000>; no-map; };"
RESERVED: Final = "#address-cells = <2>; #size-cells = <2>; ranges;"
UART: Final = "interrupt-parent = <0x03>;\n\t\t\tinterrupts = <0x01 0x04>;"
UART_REG: Final = "reg = <0x00 0x10000000 0x00 0x100>;"
PLIC_REG: Final = "reg = <0x00 0xc000000 0x00 0x1000000>;"
MEMORY: Final = "reg = <0x00 0x80000000 0x00 0x80000000>;"
HTIF: Final = 'compatible = "ucb,htif0";'
COMPATIBLE: Final = (
    'compatible = "anulum,loop-timing-witness-axi-v1", "anulum,witness-isa-simulation";'
)
HEADER: Final = "/dts-v1/;"
EXTRA_MEMORY: Final = "    witness@40000000 {"
CASES: Final[dict[str, tuple[tuple[tuple[str, str], ...], dict[str, Any]]]] = {
    "spike platform": ((), {}),
    "same firmware and telemetry": ((), {"shared": SELECTION["firmware"]}),
    "no mailbox": ((), {"mailbox": 0}),
    "stack below a page": ((), {"stack": 4080}),
    "stack not aligned": ((), {"stack": 4104}),
    "reserved-memory without ranges": (
        ((RESERVED, "#address-cells = <2>; #size-cells = <2>;"),),
        {},
    ),
    "reserved-memory size cells differ": (
        ((RESERVED, "#address-cells = <2>; #size-cells = <1>; ranges;"),),
        {},
    ),
    "reserved-memory without size cells": (((RESERVED, "#address-cells = <2>; ranges;"),), {}),
    "firmware not a reservation": ((), {"firmware": "/memory@80000000"}),
    "firmware missing": ((), {"firmware": "/reserved-memory/absent"}),
    "firmware mapped": (((FIRMWARE, FIRMWARE.replace(" no-map;", "")),), {}),
    "firmware reusable": (((FIRMWARE, FIRMWARE.replace("no-map;", "no-map; reusable;")),), {}),
    "firmware disabled": (
        ((FIRMWARE, FIRMWARE.replace("no-map;", 'no-map; status = "disabled";')),),
        {},
    ),
    "firmware ok status": (
        ((FIRMWARE, FIRMWARE.replace("no-map;", 'no-map; status = "ok";')),),
        {},
    ),
    "firmware two extents": (
        ((FIRMWARE, FIRMWARE.replace("0x80000>", "0x40000 0 0x80040000 0 0x40000>")),),
        {},
    ),
    "firmware not page aligned": (((FIRMWARE, FIRMWARE.replace("0x80000>", "0x80100>")),), {}),
    "reservations overlap": (((TELEMETRY, TELEMETRY.replace("0x80080000 0", "0x80040000 0")),), {}),
    "mailbox beyond telemetry": ((), {"mailbox": 0x10001}),
    "stack beyond firmware": ((), {"stack": 0x80010}),
    "backing RAM not memory": ((), {"ram": "/soc"}),
    "backing RAM disabled": (((MEMORY, MEMORY + ' status = "disabled";'),), {}),
    "reservation outside RAM": (((MEMORY, "reg = <0x00 0x80040000 0x00 0x7ffc0000>;"),), {}),
    "RAM banks overlap a reservation twice": (
        ((MEMORY, "reg = <0x00 0x80000000 0x00 0x80000000 0x00 0x80000000 0x00 0x100000>;"),),
        {},
    ),
    "another memory node over firmware": (
        (
            (
                EXTRA_MEMORY,
                (
                    '    memory@90000000 { device_type = "memory"; '
                    "reg = <0 0x80000000 0 0x1000>; };\n    witness@40000000 {"
                ),
            ),
        ),
        {},
    ),
    "another reservation over firmware": (
        ((TELEMETRY, TELEMETRY + " other@80000000 { reg = <0 0x80001000 0 0x1000>; };"),),
        {},
    ),
    "header reservation over firmware": (
        ((HEADER, HEADER + "\n/memreserve/ 0x80001000 0x1000;"),),
        {},
    ),
    "header reservation equal to firmware": (
        ((HEADER, HEADER + "\n/memreserve/ 0x80000000 0x80000;"),),
        {},
    ),
    "device missing": ((), {"device": "/absent"}),
    "device disabled": (((WITNESS, WITNESS + ' status = "disabled";'),), {}),
    "device without compatible": (
        (
            (
                COMPATIBLE,
                "",
            ),
        ),
        {},
    ),
    "device of another version": (
        (("loop-timing-witness-axi-v1", "loop-timing-witness-axi-v2"),),
        {},
    ),
    "extended interrupt": (
        ((WITNESS, "reg = <0 0x40000000 0 256>; interrupts-extended = <3 2>;"),),
        {},
    ),
    "extended and plain interrupts": (((WITNESS, WITNESS + " interrupts-extended = <3 2>;"),), {}),
    "extended interrupt with two sources": (
        ((WITNESS, "reg = <0 0x40000000 0 256>; interrupts-extended = <3 2 3 5>;"),),
        {},
    ),
    "device without interrupt parent": (
        ((WITNESS, "reg = <0 0x40000000 0 256>; interrupts = <2>;"),),
        {},
    ),
    "device interrupt parent undeclared": (((WITNESS, WITNESS.replace("<3>", "<9>")),), {}),
    "device source differs": (((WITNESS, WITNESS.replace("<2>", "<5>")),), {}),
    "selected PLIC is another controller": ((), {"plic": "/cpus/cpu@0/interrupt-controller"}),
    "selected hart has no context": ((), {"hart": 7}),
    "aperture of half size": (((WITNESS, WITNESS.replace("0 256>", "0 128>")),), {}),
    "aperture not aligned": (
        ((WITNESS, WITNESS.replace("0x40000000 0 256", "0x40000080 0 256")),),
        {},
    ),
    "aperture inside the PLIC": (((WITNESS, WITNESS.replace("0x40000000", "0xc000000")),), {}),
    "another consumer of the source": (((UART, UART.replace("0x01 0x04", "0x01 0x02")),), {}),
    "another extended consumer of the source": (
        ((UART, "interrupts-extended = <0x03 0x02>;"),),
        {},
    ),
    "consumer with both forms": (
        ((UART, UART + "\n\t\t\tinterrupts-extended = <0x03 0x05>;"),),
        {},
    ),
    "consumer of an undeclared controller": (((UART, "interrupts-extended = <0x09 0x05>;"),), {}),
    "consumer specifier truncated": (((UART, "interrupts-extended = <0x03>;"),), {}),
    "consumer of a non-controller": (
        (
            (UART, UART.replace("<0x03>", "<0x04>")),
            (HTIF, HTIF + " phandle = <4>; #interrupt-cells = <1>;"),
        ),
        {},
    ),
    "consumer without a parent": (((HTIF, HTIF + " interrupts = <1>;"),), {}),
    "consumer of a wide controller": (
        (
            (UART, "interrupt-parent = <0x04>;\n\t\t\tinterrupts = <1 2 3 4 5>;"),
            (HTIF, HTIF + " interrupt-controller; #interrupt-cells = <5>; phandle = <4>;"),
        ),
        {},
    ),
    "consumer specifier not whole": (
        (
            (UART, "interrupt-parent = <0x04>;\n\t\t\tinterrupts = <1 2 3>;"),
            (HTIF, HTIF + " interrupt-controller; #interrupt-cells = <2>; phandle = <4>;"),
        ),
        {},
    ),
    "extended interrupt with a parent": (
        (
            (
                WITNESS,
                "reg = <0 0x40000000 0 256>; interrupt-parent = <3>; interrupts-extended = <3 2>;",
            ),
        ),
        {},
    ),
    "root without size cells": ((("\t#size-cells = <0x02>;\n\tcompatible", "\tcompatible"),), {}),
    "firmware at address zero": (((FIRMWARE, FIRMWARE.replace("0x80000000 0", "0 0")),), {}),
    "firmware of no size": (((FIRMWARE, FIRMWARE.replace("0x80000>", "0>")),), {}),
    "firmware address not page aligned": (
        ((FIRMWARE, FIRMWARE.replace("0x80000000 0", "0x80000100 0")),),
        {},
    ),
    "aperture at address zero": (((WITNESS, WITNESS.replace("0x40000000 0 256", "0 0 256")),), {}),
    "aperture of two extents": (
        ((WITNESS, WITNESS.replace("0 256>", "0 256 0 0x40001000 0 256>")),),
        {},
    ),
    "consumer inheriting its parent": (
        (
            (UART, "interrupts = <0x01 0x04>;"),
            (
                "\t\tranges;\n\n\t\tclint@2000000",
                "\t\tranges;\n\t\tinterrupt-parent = <0x03>;\n\n\t\tclint@2000000",
            ),
        ),
        {},
    ),
    "device inheriting its parent": (
        (
            (WITNESS, "reg = <0 0x40000000 0 256>; interrupts = <2>;"),
            (
                "\t#size-cells = <0x02>;\n\tcompatible",
                "\t#size-cells = <0x02>;\n\tinterrupt-parent = <0x03>;\n\tcompatible",
            ),
        ),
        {},
    ),
    "another reservation ending at firmware": (
        ((TELEMETRY, TELEMETRY + " other@7ffff000 { reg = <0 0x7ffff000 0 0x1000>; };"),),
        {},
    ),
    "stack of one page": ((), {"stack": 4096}),
    "mailbox filling telemetry": ((), {"mailbox": 0x10000}),
    "stack filling firmware": ((), {"stack": 0x80000}),
    "RAM bank ending inside firmware": (((MEMORY, "reg = <0x00 0x80000000 0x00 0x40000>;"),), {}),
    "RAM banks leaving the firmware end uncovered": (
        ((MEMORY, "reg = <0x00 0x80000000 0x00 0x40000 0x00 0x80080000 0x00 0x10000>;"),),
        {},
    ),
    "PLIC over another memory node": (
        (
            (
                EXTRA_MEMORY,
                (
                    '    memory@c000000 { device_type = "memory"; '
                    "reg = <0 0xc000000 0 0x1000>; };\n    witness@40000000 {"
                ),
            ),
        ),
        {},
    ),
    "consumer parent undeclared": (((UART, UART.replace("<0x03>", "<0x09>")),), {}),
    "another reservation beside firmware": (
        ((TELEMETRY, TELEMETRY + " other@80090000 { reg = <0 0x80090000 0 0x1000>; };"),),
        {},
    ),
    "another memory node elsewhere": (
        (
            (
                EXTRA_MEMORY,
                (
                    '    memory@100000000 { device_type = "memory"; '
                    "reg = <1 0 0 0x1000>; };\n    witness@40000000 {"
                ),
            ),
        ),
        {},
    ),
    "consumer specifier empty": (((UART, "interrupt-parent = <0x03>;\n\t\t\tinterrupts;"),), {}),
    "aperture over another device": (((UART_REG, "reg = <0x00 0x40000000 0x00 0x100>;"),), {}),
    "aperture over a header reservation": (
        ((HEADER, HEADER + "\n/memreserve/ 0x40000000 0x100;"),),
        {},
    ),
    "PLIC inside RAM": (((PLIC_REG, "reg = <0x00 0x90000000 0x00 0x1000000>;"),), {}),
    "PLIC over a header reservation": (
        ((HEADER, HEADER + "\n/memreserve/ 0xc000000 0x1000;"),),
        {},
    ),
}


def _selection(overrides: dict[str, Any]) -> tuple[MemorySelection, str, PlicSelection]:
    """Return the bind arguments of a case.

    Parameters
    ----------
    overrides
        Selection members that differ from the ISA image's.

    Returns
    -------
    tuple[MemorySelection, str, PlicSelection]
        Memory selection, device path and PLIC selection.
    """
    chosen = {**SELECTION, **overrides}
    memory = MemorySelection(
        chosen["ram"], chosen["firmware"], chosen["shared"], chosen["mailbox"], chosen["stack"]
    )
    plic = PlicSelection(chosen["plic"], chosen["hart"], chosen["source"], chosen["layout"])
    return memory, chosen["device"], plic


def _ranges(base: bytes, blob: bytes) -> list[list[Any]]:
    """Return the byte ranges of the base that a blob replaces.

    Parameters
    ----------
    base
        Base blob.
    blob
        Case blob.

    Returns
    -------
    list[list[Any]]
        ``[start, end, hex]`` replacements in base order.
    """
    matcher = difflib.SequenceMatcher(None, base, blob, autojunk=False)
    return [
        [first, last, blob[start:end].hex()]
        for tag, first, last, start, end in matcher.get_opcodes()
        if tag != "equal"
    ]


def _outcome(blob: bytes, overrides: dict[str, Any]) -> dict[str, Any]:
    """Bind one case and return the platform as ``asdict`` writes it, or the refusal.

    Parameters
    ----------
    blob
        Compiled platform.
    overrides
        Selection members that differ from the ISA image's.

    Returns
    -------
    dict[str, Any]
        ``{"platform": ...}`` or ``{"refusal": text}``.
    """
    memory, device, plic = _selection(overrides)
    try:
        platform = bind_platform(decode_device_tree(blob), memory, device, plic)
    except ValueError as error:
        return {"refusal": str(error)}
    return {"platform": asdict(platform)}


def corpus(directory: Path) -> dict[str, Any]:
    """Compile every case and return the corpus.

    Parameters
    ----------
    directory
        Owned directory for the compiler's files.

    Returns
    -------
    dict[str, Any]
        The base blob, the selection and the cases.
    """
    source = _platform()
    base = _compile(source, directory, force=False)
    cases = []
    for name, (changes, overrides) in CASES.items():
        blob = _compile(_changed(source, changes, name), directory, force=False)
        item = {"name": name, "blob": _ranges(base, blob), "selection": overrides}
        cases.append({**item, **_outcome(blob, overrides)})
    return {
        "schema": "loop-timing-witness.amp-platform-cases.v1",
        "description": (
            "Python's bind_platform on the Spike platform compiled by dtc, changed per case. A "
            "case's blob is the base with [start, end, hex] byte ranges replaced; its selection "
            "overrides members of the ISA image's selection. platform is dataclasses.asdict of "
            "the result, refusal Python's text."
        ),
        "base": base.hex(),
        "selection": SELECTION,
        "cases": cases,
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
    """Rebuild the corpus with the real ``dtc`` and Python's binding and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the compiler's files.
    """
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
