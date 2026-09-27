# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete native raw tracking ABI validation

"""Decode bounded native integer observations before writing converted tracking."""

from __future__ import annotations

import csv
import io
from decimal import Context, Decimal, localcontext
from typing import Final

FIELDS: Final = (
    "cycle",
    "reference_raw",
    "output_raw",
    "velocity_raw",
    "command_raw",
    "integral_raw",
    "derivative_raw",
    "clipped",
    "integral_held",
    "submitted",
    "sample_ticks",
    "irq_generation",
    "overload_work",
)
BOUNDS: Final = {
    **dict.fromkeys(FIELDS[1:7], (-(1 << 31), (1 << 31) - 1)),
    **dict.fromkeys(FIELDS[7:10], (0, 1)),
    **dict.fromkeys(FIELDS[10:], (0, (1 << 64) - 1)),
}


def _integer(text: object, low: int, high: int) -> int:
    """Parse one nonempty ASCII decimal token within its native field bounds.

    Parameters
    ----------
    text
        Actual CSV cell, potentially absent in an incomplete row.
    low
        Inclusive ABI lower bound.
    high
        Inclusive ABI upper bound.

    Returns
    -------
    int
        Validated integer observation.

    Raises
    ------
    ValueError
        If the field is missing, not ASCII decimal or outside its bounds.
    """
    if not isinstance(text, str) or not text:
        message = "native tracking contains an incomplete row"
        raise ValueError(message)
    digits = text.removeprefix("-")
    if not digits.isascii() or not digits.isdecimal():
        message = "native tracking integer is not ASCII decimal"
        raise ValueError(message)
    value = int(text)
    if not low <= value <= high:
        message = "native tracking integer is outside its ABI bounds"
        raise ValueError(message)
    return value


def decode_tracking(content: bytes, cycles: int, sample_count: int) -> list[list[int | Decimal]]:
    """Validate every raw ABI column and preserve only actual ordered observations.

    Parameters
    ----------
    content
        Hash-verified original raw tracking bytes.
    cycles
        Validated native configured cycle count.
    sample_count
        Actual native completion sample count.

    Returns
    -------
    list of list of int or Decimal
        Exact cycle/reference/output observations in Q8.24-derived units.

    Raises
    ------
    ValueError
        If header, rows, integers, cycle ordering or completion counts disagree.
    """
    converted: list[list[int | Decimal]] = []
    previous = -1
    try:
        with (
            localcontext(Context(prec=32)),
            io.StringIO(content.decode("utf-8"), newline="") as stream,
        ):
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != list(FIELDS):
                message = "native tracking header does not match the raw controller ABI"
                raise ValueError(message)
            for row in reader:
                if None in row:
                    message = "native tracking contains an incomplete row"
                    raise ValueError(message)
                values = {
                    name: _integer(
                        row[name], *((0, cycles - 1) if name == "cycle" else BOUNDS[name])
                    )
                    for name in FIELDS
                }
                cycle = values["cycle"]
                if cycle <= previous:
                    message = "native tracking cycles must be unique and increasing"
                    raise ValueError(message)
                previous = cycle
                converted.append(
                    [
                        cycle,
                        Decimal(values["reference_raw"]) / (1 << 24),
                        Decimal(values["output_raw"]) / (1 << 24),
                    ]
                )
    except csv.Error as error:
        message = "native tracking contains malformed CSV"
        raise ValueError(message) from error
    if len(converted) != sample_count:
        message = "native sample count does not match tracking rows"
        raise ValueError(message)
    return converted
