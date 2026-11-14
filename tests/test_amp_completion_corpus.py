# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP completion and capture stream corpus shared with the native analysis

"""Hold Python's AMP completion, raw tracking and capture agreement in a shared corpus.

The base streams are the real ISA capture of ``tests/test_amp_completion.py``
(hart 2 with production RTL): its simulator log line, its 40 events and its
10 raw tracking rows, with the repository's measurement domain. The cases
change the log (line ends, the prefix, the JSON, the members, the flags and
each counter at its bounds), the raw tracking (header, cells, syntax, every
column's bounds, leading zeros and long magnitudes, cycle order, CSV quoting
and errors, encoding and the sample count) and the capture (the retained
domain, the event stream, the completion's counters and the order in which
defects are met).

Logs and tracking are written as Latin-1 text, one character per byte, and
events as hexadecimal bytes; a capture case's domain is ``null`` for the
repository's. Tracking rows are ``[cycle, reference_raw, output_raw]``: the
raw values Python's decoded Q8.24 decimals hold exactly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from decimal import Decimal
from functools import partial
from typing import TYPE_CHECKING, Any, Final

from amp_completion import completion_receipt, validate_capture
from test_amp_completion import EVENTS, LOG, TRACKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.native_tracking import FIELDS, decode_tracking

if TYPE_CHECKING:
    from collections.abc import Callable

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-completion-cases.json"
DOMAIN: Final = (REPOSITORY_ROOT / "measurement-domain.json").read_bytes()
PREFIX: Final = b"WITNESS_AMP_COMPLETION "
RECEIPT: Final = b'{"samples":10,"events":40,"misses":0,"overflow":0,"safe":false,"thermal":false}'
ROWS: Final = TRACKING.decode("ascii").splitlines()
SCALE: Final = 1 << 24


def _log(**members: object) -> bytes:
    """Return a one-line log whose completion has members replaced or removed.

    Parameters
    ----------
    **members
        New values; ``...`` removes a member.

    Returns
    -------
    bytes
        The log.
    """
    data = json.loads(RECEIPT)
    for name, value in members.items():
        if value is ...:
            del data[name]
        else:
            data[name] = value
    return PREFIX + json.dumps(data, separators=(",", ":")).encode("ascii") + b"\n"


def _receipt_cases() -> dict[str, bytes]:
    """Return the simulator log cases.

    Returns
    -------
    dict[str, bytes]
        Log by case name.
    """
    line = PREFIX + RECEIPT
    return {
        "ISA logger line": LOG,
        "empty log": b"",
        "exit line only": b"exit 0\n",
        "two completion lines": LOG + LOG,
        "completion among other lines": b"boot\r\n" + line + b"\rexit 0\n",
        "completion without a line end": line,
        "completion after a lone carriage return": b"boot\r" + line,
        "completion inside a line": b"log " + line + b"\n",
        "prefix without its space": line.replace(b"COMPLETION ", b"COMPLETION", 1),
        "completion then whitespace": line + b"  \n",
        "completion not JSON": PREFIX + b"{\n",
        "completion a list": PREFIX + b"[]\n",
        "completion with a repeated member": PREFIX + RECEIPT[:-1] + b',"safe":true}\n',
        "completion without thermal": _log(thermal=...),
        "completion with another member": _log(extra=1),
        "safe as zero": _log(safe=0),
        "thermal as text": _log(thermal="false"),
        "safe and thermal set": _log(safe=True, thermal=True),
        "samples as a float": _log(samples=10.0),
        "events negative": _log(events=-1),
        "misses as true": _log(misses=True),
        "largest misses": _log(misses=(1 << 32) - 1),
        "misses beyond 32 bits": _log(misses=1 << 32),
        "largest overflow": _log(overflow=(1 << 32) - 1),
        "overflow beyond 32 bits": _log(overflow=1 << 32),
        "largest samples and events": _log(samples=(1 << 64) - 1, events=(1 << 64) - 1),
        "events beyond 64 bits": _log(events=1 << 64),
    }


def _table(*changes: tuple[int, int, str], rows: list[str] | None = None) -> bytes:
    """Return the raw tracking with cells replaced.

    Parameters
    ----------
    *changes
        ``(row, column, text)``, rows counted from the first data row.
    rows
        Data rows instead of the captured ones.

    Returns
    -------
    bytes
        Header and rows, each ended by a newline, as UTF-8.
    """
    lines = [ROWS[0], *(ROWS[1:] if rows is None else rows)]
    for row, column, text in changes:
        cells = lines[row + 1].split(",")
        cells[column] = text
        lines[row + 1] = ",".join(cells)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _bound_cases() -> dict[str, bytes]:
    """Return the raw tracking cases at and beside every column's bounds.

    Returns
    -------
    dict[str, bytes]
        Table by case name.
    """
    cases = {
        "last cycle": _table((9, 0, "9")),
        "cycle of the run length": _table((9, 0, "10")),
        "negative cycle": _table((0, 0, "-1")),
    }
    for column in range(1, 7):
        cases |= {
            f"{FIELDS[column]} at its minimum": _table((0, column, str(-(1 << 31)))),
            f"{FIELDS[column]} below its minimum": _table((0, column, str(-(1 << 31) - 1))),
            f"{FIELDS[column]} at its maximum": _table((0, column, str((1 << 31) - 1))),
            f"{FIELDS[column]} beyond its maximum": _table((0, column, str(1 << 31))),
        }
    for column in range(7, 10):
        cases |= {
            f"{FIELDS[column]} negative": _table((0, column, "-1")),
            f"{FIELDS[column]} two": _table((0, column, "2")),
        }
    for column in range(10, 13):
        cases |= {
            f"{FIELDS[column]} at its maximum": _table((0, column, str((1 << 64) - 1))),
            f"{FIELDS[column]} beyond its maximum": _table((0, column, str(1 << 64))),
            f"{FIELDS[column]} negative": _table((0, column, "-1")),
        }
    return cases


def _syntax_cases() -> dict[str, bytes]:
    """Return the raw tracking cases of cell syntax, row shape and CSV text.

    Returns
    -------
    dict[str, bytes]
        Table by case name.
    """
    shifted = [
        row.replace("0,", "1,", 1) if index == 0 else row for index, row in enumerate(ROWS[1:])
    ]
    return {
        "captured tracking": TRACKING,
        "cell with a plus sign": _table((0, 1, "+1")),
        "cell of a sign only": _table((0, 1, "-")),
        "cell with a decimal point": _table((0, 1, "1.5")),
        "cell in another script": _table((0, 1, chr(0x661))),
        "empty cell": _table((0, 4, "")),
        "negative zero": _table((0, 2, "-0")),
        "cell with 5000 leading zeros": _table((0, 2, "0" * 5000 + "7")),
        "cell of 5000 nines": _table((0, 11, "9" * 5000)),
        "cell of 21 significant digits": _table((0, 11, "1" + "0" * 20)),
        "quoted cell": _table((0, 2, '"7"')),
        "stray quote": _table((0, 1, 'x"y')),
        "open quote": _table((0, 1, '"7')),
        "row without its last cell": _table(rows=[ROWS[1].rsplit(",", 1)[0], *ROWS[2:]]),
        "row with an extra cell": _table(rows=[ROWS[1] + ",0", *ROWS[2:]]),
        "extra cell after a bad cell": _table(rows=["x" + ROWS[1] + ",0", *ROWS[2:]]),
        "bad cell before a missing cell": _table(
            rows=["x," + ROWS[1].split(",", 1)[1].rsplit(",", 1)[0], *ROWS[2:]]
        ),
        "repeated cycle": _table(rows=shifted),
        "decreasing cycles": _table(rows=[ROWS[2], ROWS[1], *ROWS[3:]]),
        "blank lines between rows": (
            "\n".join([ROWS[0], ROWS[1], "", *ROWS[2:]]) + "\n\n"
        ).encode(),
        "rows ended by CRLF": ("\r\n".join(ROWS) + "\r\n").encode(),
        "header only": (ROWS[0] + "\n").encode(),
        "empty": b"",
        "blank first line": ("\n" + "\n".join(ROWS) + "\n").encode(),
        "header with a byte order mark": ("﻿" + "\n".join(ROWS) + "\n").encode("utf-8"),
        "header with another column": ("\n".join([ROWS[0] + ",extra", *ROWS[1:]]) + "\n").encode(),
        "not UTF-8": TRACKING + b"\xff\n",
    }


def _capture(
    events: bytes = EVENTS,
    tracking: bytes = TRACKING,
    domain: object = None,
    completion: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return one capture case.

    Parameters
    ----------
    events
        Event stream.
    tracking
        Raw tracking.
    domain
        Retained domain: ``None`` for the repository's, a document, or bytes.
    completion
        Counter changes of the logged completion.

    Returns
    -------
    dict[str, Any]
        The case as the corpus writes it.
    """
    if domain is None or isinstance(domain, bytes):
        text = None if domain is None else domain.decode("latin-1")
    else:
        text = json.dumps(domain)
    return {
        "completion": completion or {},
        "events": events.hex(),
        "tracking": tracking.decode("latin-1"),
        "domain": text,
    }


def _capture_cases() -> dict[str, dict[str, Any]]:
    """Return the capture cases.

    Returns
    -------
    dict[str, dict[str, Any]]
        Case by name.
    """
    document = json.loads(DOMAIN)
    broken = {**document, "design_contracts": {**document["design_contracts"], "event_record": 5}}
    shorter = _table(rows=ROWS[1:-1])
    return {
        "ISA capture": _capture(),
        "empty domain": _capture(domain={}),
        "domain with a number for contracts": _capture(domain={"design_contracts": 5}),
        "domain breaking its record": _capture(domain=broken),
        "domain not JSON": _capture(domain=b"{"),
        "domain error before events error": _capture(events=b"", domain={}),
        "no events": _capture(events=b""),
        "events not whole records": _capture(events=EVENTS[:-1]),
        "reserved event byte": _capture(events=EVENTS[:1] + b"\x01" + EVENTS[2:]),
        "one event lost": _capture(events=EVENTS[:16] + EVENTS[32:], completion={"events": 39}),
        "event count one less": _capture(completion={"events": 39}),
        "sample count one less": _capture(completion={"samples": 9}),
        "tracking without its last row": _capture(tracking=shorter, completion={"samples": 9}),
        "overflow": _capture(completion={"overflow": 1}),
        "overflow and a count mismatch": _capture(completion={"overflow": 1, "events": 39}),
        "tracking error before overflow": _capture(
            tracking=TRACKING + b"\xff", completion={"overflow": 1}
        ),
        "events error before tracking error": _capture(events=b"", tracking=b""),
    }


def _refusal(work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run one Python reader and return its value or its refusal.

    Parameters
    ----------
    work
        Callable returning the outcome document.

    Returns
    -------
    dict[str, Any]
        The outcome document or ``{"refusal": text}``.
    """
    try:
        result: dict[str, Any] = work()
    except ValueError as error:
        return {"refusal": str(error)}
    return result


def _completion(log: bytes) -> dict[str, Any]:
    """Read the completion of one simulator log.

    Parameters
    ----------
    log
        Simulator log.

    Returns
    -------
    dict[str, Any]
        The completion as ``dataclasses.asdict`` writes it.
    """
    return {"completion": asdict(completion_receipt(log))}


def _rows(content: bytes) -> dict[str, Any]:
    """Decode a raw tracking table with 10 samples of 10 cycles.

    Parameters
    ----------
    content
        Raw tracking.

    Returns
    -------
    dict[str, Any]
        The rows as raw values.
    """
    rows = []
    for cycle, reference, output in decode_tracking(content, 10, 10):
        raw = [int(Decimal(value) * SCALE) for value in (reference, output)]
        assert [Decimal(value) / SCALE for value in raw] == [reference, output]
        rows.append([cycle, *raw])
    return {"rows": rows}


def _checked(case: dict[str, Any]) -> dict[str, Any]:
    """Run ``validate_capture`` on one capture case.

    Parameters
    ----------
    case
        The case.

    Returns
    -------
    dict[str, Any]
        ``{"value": true}``.
    """
    completion = replace(completion_receipt(LOG), **case["completion"])
    domain = DOMAIN if case["domain"] is None else case["domain"].encode("latin-1")
    validate_capture(
        completion,
        bytes.fromhex(case["events"]),
        case["tracking"].encode("latin-1"),
        domain,
        10,
    )
    return {"value": True}


def corpus() -> dict[str, Any]:
    """Run every case and return the corpus.

    Returns
    -------
    dict[str, Any]
        The receipt, tracking and capture cases with their outcomes.
    """
    tables = _syntax_cases() | _bound_cases()
    return {
        "schema": "loop-timing-witness.amp-completion-cases.v1",
        "description": (
            "Python's completion_receipt on simulator logs, decode_tracking on raw tracking (10 "
            "cycles, 10 samples) and validate_capture on the real ISA capture changed per case. "
            "Logs and tracking are Latin-1 text; events are hexadecimal; a null domain is the "
            "repository's measurement domain. rows are [cycle, reference_raw, output_raw]."
        ),
        "receipts": [
            {
                "name": name,
                "log": log.decode("latin-1"),
                **_refusal(partial(_completion, log)),
            }
            for name, log in _receipt_cases().items()
        ],
        "tracking": [
            {
                "name": name,
                "content": content.decode("latin-1"),
                **_refusal(partial(_rows, content)),
            }
            for name, content in tables.items()
        ],
        "captures": [
            {"name": name, **case, **_refusal(partial(_checked, case))}
            for name, case in _capture_cases().items()
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
    """Rebuild the corpus with Python's readers and require the committed file."""
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus())
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
