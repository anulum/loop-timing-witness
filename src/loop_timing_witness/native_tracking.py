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
from typing import Any, Final

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
SIGNIFICANT_DIGITS: Final = len(str((1 << 64) - 1))


def _integer(text: object, low: int, high: int) -> int:
    """Parse one nonempty ASCII decimal token within its native field bounds.

    Leading zeros are accepted at any length; a magnitude with more significant digits than
    any bound is outside every bound and is refused before conversion.

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
    significant = digits.lstrip("0") or "0"
    if len(significant) <= SIGNIFICANT_DIGITS:
        value = -int(significant) if text.startswith("-") else int(significant)
        if low <= value <= high:
            return value
    message = "native tracking integer is outside its ABI bounds"
    raise ValueError(message)


def _row_values(row: dict[str | Any, str | Any], cycles: int) -> dict[str, int]:
    """Decode one complete raw tracking row within its ABI bounds.

    Parameters
    ----------
    row
        One CSV row keyed by header name.
    cycles
        Validated native configured cycle count.

    Returns
    -------
    dict[str, int]
        Exact integer value of every ABI column.

    Raises
    ------
    ValueError
        If the row is incomplete or a value is not an integer within its bounds.
    """
    if None in row:
        message = "native tracking contains an incomplete row"
        raise ValueError(message)
    return {
        name: _integer(row[name], *((0, cycles - 1) if name == "cycle" else BOUNDS[name]))
        for name in FIELDS
    }


def _converted_rows(reader: csv.DictReader[str], cycles: int) -> list[list[int | Decimal]]:
    """Convert every raw row in cycle order to exact Q8.24-derived values.

    Parameters
    ----------
    reader
        Strict CSV reader over the decoded tracking text, inside a 32-digit context.
    cycles
        Validated native configured cycle count.

    Returns
    -------
    list of list of int or Decimal
        Exact cycle, reference and output of every row.

    Raises
    ------
    ValueError
        If the header is not the raw ABI, a row is invalid or cycles do not increase.
    csv.Error
        If the CSV text is malformed.
    """
    if reader.fieldnames != list(FIELDS):
        message = "native tracking header does not match the raw controller ABI"
        raise ValueError(message)
    converted: list[list[int | Decimal]] = []
    previous = -1
    for row in reader:
        values = _row_values(row, cycles)
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
    return converted


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
        If the bytes are not UTF-8, or header, rows, integers, cycle ordering or completion
        counts disagree.
    """
    try:
        with (
            localcontext(Context(prec=32)),
            io.StringIO(content.decode("utf-8"), newline="") as stream,
        ):
            converted = _converted_rows(csv.DictReader(stream, strict=True), cycles)
    except UnicodeDecodeError as error:
        message = "native tracking is not UTF-8"
        raise ValueError(message) from error
    except csv.Error as error:
        message = "native tracking contains malformed CSV"
        raise ValueError(message) from error
    if len(converted) != sample_count:
        message = "native sample count does not match tracking rows"
        raise ValueError(message)
    return converted
