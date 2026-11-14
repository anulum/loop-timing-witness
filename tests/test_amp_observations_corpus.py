# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP tracking CSV and fault schedule corpus shared with the native analysis

"""Hold Python's observed tracking CSV and fault schedule in a shared corpus.

``decimals`` holds ``str(Decimal(raw) / 2**24)`` for a sweep of raw Q8.24
values: every power of two and its neighbours, both signs, the 32-bit
extremes, the whole multiples of ten and a fixed pseudo-random spread. ``tables`` holds
``tracking_csv`` on the real ISA capture's raw tracking and on tables of
extreme and threshold values, and two refusals. ``schedules`` holds
``fault_schedule`` on every configuration of the run input corpus and on
fault fields written with signs and leading zeros. Texts are Latin-1, one
character per byte.
"""

from __future__ import annotations

import json
from decimal import Context, Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final

from amp_capture_observations import fault_schedule, tracking_csv
from test_amp_completion import TRACKING
from test_amp_image_flow import CONFIGURATION

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from collections.abc import Callable

DATA: Final = REPOSITORY_ROOT / "analysis/rust/tests/data"
CORPUS: Final = DATA / "amp-observations-cases.json"
SCALE: Final = 1 << 24
HEADER: Final = TRACKING.decode("ascii").splitlines()[0]


def _raws() -> list[int]:
    """Return the raw values of the decimal sweep, in ascending order.

    Returns
    -------
    list[int]
        Distinct 32-bit raw values.
    """
    found = {0, -(1 << 31), (1 << 31) - 1}
    found |= {tens * 10 * SCALE for tens in range(-12, 13)}
    for power in range(31):
        for value in ((1 << power) - 1, 1 << power, (1 << power) + 1):
            found |= {value, -value}
    state = 12345
    for _ in range(500):
        state = (state * 1103515245 + 12345) % (1 << 31)
        found |= {state - (1 << 30), (state >> (state % 31)) * (1 if state % 2 else -1)}
    return sorted(value for value in found if -(1 << 31) <= value < (1 << 31))


def _decimal(raw: int) -> str:
    """Return Python's text of one raw Q8.24 value, as ``decode_tracking`` computes it.

    Parameters
    ----------
    raw
        Raw value.

    Returns
    -------
    str
        ``str(Decimal(raw) / 2**24)`` under a 32-digit context.
    """
    with localcontext(Context(prec=32)):
        return str(Decimal(raw) / SCALE)


def _table(rows: list[tuple[int, int, int]]) -> bytes:
    """Return a raw tracking table whose rows carry the given cycle, reference and output.

    Parameters
    ----------
    rows
        ``(cycle, reference_raw, output_raw)`` rows.

    Returns
    -------
    bytes
        Header and rows.
    """
    lines = [HEADER]
    for cycle, reference, output in rows:
        lines.append(f"{cycle},{reference},{output},0,0,0,0,0,0,1,1,1,0")
    return ("\n".join(lines) + "\n").encode("ascii")


def _tables() -> dict[str, tuple[bytes, int, int]]:
    """Return the ``tracking_csv`` cases: table, cycles and samples.

    Returns
    -------
    dict[str, tuple[bytes, int, int]]
        Case by name.
    """
    extremes = [(0, -(1 << 31), (1 << 31) - 1), (1, (1 << 31) - 1, -(1 << 31)), (5, 0, -1)]
    thresholds = [(cycle, 1 << cycle, -(1 << cycle)) for cycle in range(32)]
    return {
        "captured tracking": (TRACKING, 10, 10),
        "extreme values": (_table(extremes), 10, 3),
        "notation thresholds": (_table(thresholds[:31]), 32, 31),
        "no rows": (_table([]), 10, 0),
        "sample count differs": (TRACKING, 10, 9),
        "cycle beyond the run": (TRACKING, 9, 10),
    }


def _schedules() -> dict[str, bytes]:
    """Return the ``fault_schedule`` cases: every run input configuration and signed fields.

    Returns
    -------
    dict[str, bytes]
        Configuration by case name.
    """
    cases = {
        case["name"]: case["content"].encode("latin-1")
        for case in json.loads((DATA / "amp-run-input-cases.json").read_text(encoding="utf-8"))[
            "cases"
        ]
    }
    signed = {
        "delay with signed fields": b"delay +0003 0002 0 0",
        "drop with a long cycle": b"drop " + b"0" * 5000 + b"3 1 0 0",
        "overload with work": b"overload 9 7 100 0",
        "freeze in the first cycle": b"freeze 0 1 0 0",
    }
    for name, fields in signed.items():
        cases[name] = CONFIGURATION.replace(b"none 0 0 0 0", fields)
    return cases


def _outcome(work: Callable[..., object], *arguments: object) -> dict[str, Any]:
    """Run one Python function and return its value or refusal.

    Parameters
    ----------
    work
        Function.
    *arguments
        Its arguments.

    Returns
    -------
    dict[str, Any]
        ``{"value": ...}`` or ``{"refusal": text}``.
    """
    try:
        value = work(*arguments)
    except ValueError as error:
        return {"refusal": str(error)}
    return {"value": value.decode("latin-1") if isinstance(value, bytes) else value}


def corpus() -> dict[str, Any]:
    """Run every case and return the corpus.

    Returns
    -------
    dict[str, Any]
        Decimals, tables and schedules with their outcomes.
    """
    return {
        "schema": "loop-timing-witness.amp-observations-cases.v1",
        "description": (
            "Python's str(Decimal(raw) / 2**24) as [raw, text]; tracking_csv on raw tracking "
            "tables with cycles and samples; fault_schedule on run configurations. Texts are "
            "Latin-1, one character per byte; value is the CSV text or the schedule."
        ),
        "decimals": [[raw, _decimal(raw)] for raw in _raws()],
        "tables": [
            {
                "name": name,
                "content": content.decode("latin-1"),
                "cycles": cycles,
                "samples": samples,
                **_outcome(tracking_csv, content, cycles, samples),
            }
            for name, (content, cycles, samples) in _tables().items()
        ],
        "schedules": [
            {
                "name": name,
                "content": content.decode("latin-1"),
                **_outcome(fault_schedule, content),
            }
            for name, content in _schedules().items()
        ],
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


def test_committed_corpus_equals_python_outcomes() -> None:
    """Rebuild the corpus with Python's converters and require the committed file."""
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus())
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
