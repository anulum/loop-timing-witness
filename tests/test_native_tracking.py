# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real native raw ABI rejection paths

"""Reject malformed actual raw captures through the public native import surface."""

from __future__ import annotations

import csv
import hashlib
from decimal import Inexact, localcontext
from fractions import Fraction
from typing import TYPE_CHECKING

import pytest
from native_simulation_manifest import convert_tracking, native_metadata
from test_native_run import native_run
from test_native_simulation_manifest import native_capture

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_capture", "native_run"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (0, "-1"),
        (0, "32"),
        *[(field, str(value)) for field in range(1, 7) for value in (-(1 << 31) - 1, 1 << 31)],
        *[(field, str(value)) for field in range(7, 10) for value in (-1, 2)],
        *[(field, str(value)) for field in range(10, 13) for value in (-1, 1 << 64)],
        (1, "1.5"),
        (1, chr(0x0661)),
        (1, "-"),
        (1, ""),
        (12, "missing"),
        (13, "extra"),
        (0, "duplicate"),
        (1, "malformed_csv"),
    ],
)
def test_raw_abi_refusal(native_capture: Path, field: int, value: str) -> None:
    """Reject each wrong ABI field even if its mutated bytes are deliberately rehashed.

    Parameters
    ----------
    native_capture
        Completed capture from actual native controller and production RTL.
    field
        Raw column under test.
    value
        Deliberate negative-case replacement or malformed row instruction.
    """
    metadata = native_metadata(native_capture)
    raw = native_capture / "tracking_raw.csv"
    lines = raw.read_text().splitlines()
    index = 2 if value == "duplicate" else 1
    fields = lines[index].split(",")
    if value == "missing":
        fields.pop()
    elif value == "extra":
        fields.append("1")
    elif value == "malformed_csv":
        fields[field] = chr(34)
    else:
        fields[field] = "0" if value == "duplicate" else value
    lines[index] = ",".join(fields)
    raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
    content = raw.read_bytes()
    metadata["artifacts"]["tracking_raw"] = {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    with pytest.raises(ValueError, match="native tracking"):
        convert_tracking(native_capture, metadata)
    assert not (native_capture / "tracking.csv").exists()


def test_q24_precision_is_independent(native_capture: Path) -> None:
    """Preserve exact actual Q8.24 values despite restrictive caller decimal precision.

    Parameters
    ----------
    native_capture
        Actual native controller capture.
    """
    metadata = native_metadata(native_capture)
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        convert_tracking(native_capture, metadata)
        assert context.prec == 3
    with (native_capture / "tracking_raw.csv").open(newline="") as source:
        raw = list(csv.DictReader(source))
    with (native_capture / "tracking.csv").open(newline="") as source:
        converted = list(csv.DictReader(source))
    for original, row in zip(raw, converted, strict=True):
        assert int(row["cycle"]) == int(original["cycle"])
        assert Fraction(row["reference"]) == Fraction(int(original["reference_raw"]), 1 << 24)
        assert Fraction(row["output"]) == Fraction(int(original["output_raw"]), 1 << 24)
