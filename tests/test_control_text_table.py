# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native table of Python's non-printable characters

"""Hold the native analysis's non-printable table to the running interpreter.

The native analysis prints paths in failed-read refusals as CPython's ``repr``,
which escapes every character for which ``str.isprintable`` is false. Its table
must equal this interpreter's, and name the same Unicode version.
"""

from __future__ import annotations

import re
import sys
import unicodedata

from conftest import REPOSITORY_ROOT

TABLE = REPOSITORY_ROOT / "analysis/rust/src/control_printable.rs"


def _python_ranges() -> list[tuple[int, int]]:
    """Return the inclusive ranges of code points this interpreter does not print.

    Returns
    -------
    list[tuple[int, int]]
        Sorted, disjoint ranges.
    """
    ranges: list[tuple[int, int]] = []
    start = None
    for code in range(sys.maxunicode + 2):
        hidden = code <= sys.maxunicode and not chr(code).isprintable()
        if hidden and start is None:
            start = code
        elif not hidden and start is not None:
            ranges.append((start, code - 1))
            start = None
    return ranges


def test_native_table_equals_the_interpreter() -> None:
    """The committed table and Unicode version are this interpreter's."""
    source = TABLE.read_text(encoding="utf-8")
    version = re.search(r"with Unicode ([0-9.]+);", source)
    assert version is not None
    assert version.group(1) == unicodedata.unidata_version
    native = [
        (int(low, 16), int(high, 16))
        for low, high in re.findall(r"\(0x([0-9a-f]+), 0x([0-9a-f]+)\)", source)
    ]
    assert native == _python_ranges()
