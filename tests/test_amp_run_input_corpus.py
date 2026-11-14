# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP run configuration corpus shared with the native analysis

"""Hold Python's AMP run configuration reader in a shared corpus.

Every case is the ISA image's configuration with fields replaced, other
separators, or other bytes. The cases keep and break the encoding, the
separators the native stream reader skips and keeps, the field count and
controller, every field's whole decimal syntax and bounds (signs, leading
zeros and magnitudes beyond the interpreter's integer string limit
included), the fault kinds and schedule, the run's integer contract and the
controller invariants, and the order in which defects are met.

A case's content is written as Latin-1 text, one character per byte; an
outcome is the run as ``dataclasses.asdict`` writes it, with the
coefficients as a list, or Python's refusal text.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Final

from amp_run_input import read_amp_run
from test_amp_image_flow import CONFIGURATION

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_contract import MAX_DURATION_TICKS, UINT32_MAX

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-run-input-cases.json"
WORDS: Final = CONFIGURATION.decode("ascii").split()
LONGEST: Final = MAX_DURATION_TICKS // UINT32_MAX
ZEROS: Final = "0" * 5000


def _words(changes: dict[int, str], separator: str = " ") -> bytes:
    """Return the ISA image's configuration with fields replaced.

    Parameters
    ----------
    changes
        Replacement text by field index.
    separator
        Text between fields.

    Returns
    -------
    bytes
        The configuration as Latin-1 bytes.
    """
    words = list(WORDS)
    for index, word in changes.items():
        words[index] = word
    return separator.join(words).encode("latin-1")


def _schedule(fault: str, fields: str) -> bytes:
    """Return the configuration with another fault kind and schedule.

    Parameters
    ----------
    fault
        Fault kind field.
    fields
        Cycle, periods, overload and modeled latency fields.

    Returns
    -------
    bytes
        The configuration.
    """
    return _words(dict(enumerate([fault, *fields.split()], start=19)))


def _layout_cases() -> dict[str, bytes]:
    """Return the encoding, separator, field count and controller cases.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    joined = [WORDS[0] + "{}" + WORDS[1], *WORDS[2:]]
    inside = " ".join(joined)
    cases = {
        "ISA image configuration": CONFIGURATION,
        "lqr controller": _words({0: "lqr"}),
        "leading and trailing whitespace": b" \t" + CONFIGURATION + b"\r\n\x0b\x0c",
        "non-ASCII byte at the end": CONFIGURATION + b"\xff",
        "non-ASCII byte first": b"\x80" + CONFIGURATION,
        "next-line byte separating fields": _words({}, "\x85"),
        "NUL inside a field": _words({1: "1\x000"}),
        "empty": b"",
        "whitespace only": b" \n\x0b",
        "23 fields": " ".join(WORDS[:-1]).encode("ascii"),
        "25 fields": CONFIGURATION + b" 0",
        "upper-case controller": _words({0: "PID"}),
        "signed controller": _words({0: "+pid"}),
        "other controller": _words({0: "other"}),
    }
    for name, separator in [
        ("tab", "\t"),
        ("newline", "\n"),
        ("carriage return", "\r"),
        ("CRLF", "\r\n"),
        ("vertical tab", "\x0b"),
        ("form feed", "\x0c"),
    ]:
        cases[f"{name} separated"] = _words({}, separator)
    for name, separator in [
        ("file", "\x1c"),
        ("group", "\x1d"),
        ("record", "\x1e"),
        ("unit", "\x1f"),
    ]:
        cases[f"{name} separator inside a field"] = inside.format(separator).encode("ascii")
        cases[f"{name} separator after the last field"] = (
            CONFIGURATION.rstrip() + separator.encode()
        )
    return cases


def _syntax_cases() -> dict[str, bytes]:
    """Return the whole decimal syntax cases.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    texts = ["1.0", "0x10", "1e3", "+", "-", "+-1", "--1", "1+", "1-0", "++1"]
    cases = {f"cycles {text}": _words({1: text}) for text in texts}
    cases |= {
        "cycles with a plus sign": _words({1: "+10"}),
        "cycles with leading zeros": _words({1: "+0010"}),
        "cycles with 5000 leading zeros": _words({1: ZEROS + "10"}),
        "negative zero cycles": _words({1: "-0"}),
        "reference amplitude not a number": _words({15: "x"}),
        "modeled latency not whole": _words({23: "1.5"}),
    }
    return cases


def _bound_cases() -> dict[str, bytes]:
    """Return the field bound cases.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    return {
        "negative cycles": _words({1: "-1"}),
        "largest cycles": _words({1: "4294967295", 2: "1"}),
        "largest cycles with leading zeros": _words({1: "00000004294967295", 2: "1"}),
        "cycles beyond 32 bits": _words({1: "4294967296"}),
        "cycles of eleven digits": _words({1: "10000000000"}),
        "cycles of 5000 digits": _words({1: "9" * 5000}),
        "smallest free coefficient": _words({7: "-2147483648"}),
        "free coefficient below 32 bits": _words({7: "-2147483649"}),
        "largest free coefficient": _words({7: "2147483647"}),
        "free coefficient beyond 32 bits": _words({7: "2147483648"}),
        "free coefficient with 5000 leading zeros": _words({7: "-" + ZEROS + "1"}),
        "free coefficient of eleven digits": _words({7: "-10000000000"}),
        "largest reference mode": _words({14: "2"}),
        "reference mode 3": _words({14: "3"}),
        "negative reference mode": _words({14: "-1"}),
        "negative zero reference mode": _words({14: "-0"}),
        "reference ramp beyond 32 bits": _words({17: "2147483648"}),
        "reference offset below 32 bits": _words({16: "-2147483649"}),
        "largest phase": _words({18: "15"}),
        "phase 16": _words({18: "16"}),
        "fault periods beyond 32 bits": _schedule("delay", "3 4294967296 0 0"),
    }


def _schedule_cases() -> dict[str, bytes]:
    """Return the fault kind and schedule cases.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    cases = {f"{fault} fault": _schedule(fault, "3 1 0 0") for fault in ("drop", "delay", "freeze")}
    return cases | {
        "overload fault": _schedule("overload", "3 1 100 0"),
        "overload fault without work": _schedule("overload", "3 1 0 0"),
        "upper-case fault kind": _schedule("NONE", "0 0 0 0"),
        "other fault kind": _schedule("other", "0 0 0 0"),
        "no fault with a cycle": _schedule("none", "1 0 0 0"),
        "no fault with periods": _schedule("none", "0 1 0 0"),
        "no fault with work": _schedule("none", "0 0 1 0"),
        "no fault with modeled latency": _schedule("none", "0 0 0 1"),
        "fault in the last cycle": _schedule("drop", "9 1 0 0"),
        "fault after the run": _schedule("drop", "10 1 0 0"),
        "fault without periods": _schedule("drop", "3 0 0 0"),
        "delay with work": _schedule("delay", "3 1 1 0"),
        "overload with modeled latency": _schedule("overload", "3 1 100 1"),
        "largest overload work": _schedule("overload", "3 1 10000000 0"),
        "overload work beyond the limit": _schedule("overload", "3 1 10000001 0"),
        "overload work of 32 bits": _schedule("overload", "3 1 4294967295 0"),
    }


def _contract_cases() -> dict[str, bytes]:
    """Return the run contract and controller invariant cases.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    cases = {
        "zero cycles": _words({1: "0"}),
        "zero period": _words({2: "0"}),
        "longest run": _words({1: str(UINT32_MAX), 2: str(LONGEST)}),
        "run beyond the timer": _words({1: str(UINT32_MAX), 2: str(LONGEST + 1)}),
        "largest periods": _words({1: "1", 2: str(UINT32_MAX)}),
    }
    for name, index, value in [
        ("negative proportional gain", 3, "-1"),
        ("zero proportional gain", 3, "0"),
        ("negative integral gain", 4, "-1"),
        ("zero integral gain", 4, "0"),
        ("negative decay", 5, "-1"),
        ("zero decay", 5, "0"),
        ("decay of one", 5, "16777216"),
        ("decay above one", 5, "16777217"),
        ("negative derivative gain", 6, "-1"),
        ("zero derivative gain", 6, "0"),
        ("positive lower limit", 10, "1"),
        ("zero lower limit", 10, "0"),
        ("negative upper limit", 11, "-1"),
        ("zero upper limit", 11, "0"),
        ("positive integral lower limit", 12, "1"),
        ("zero integral lower limit", 12, "0"),
        ("negative integral upper limit", 13, "-1"),
        ("zero integral upper limit", 13, "0"),
    ]:
        cases[name] = _words({index: value})
    return cases


def _order_cases() -> dict[str, bytes]:
    """Return cases with two defects, where the first met is reported.

    Returns
    -------
    dict[str, bytes]
        Content by case name.
    """
    return {
        "count before syntax": CONFIGURATION + b" x",
        "controller before syntax": _words({0: "other", 1: "x"}),
        "syntax before a later bound": _words({1: "x", 2: "-1"}),
        "bound before a later syntax": _words({1: "-1", 2: "x"}),
        "phase before fault kind": _words({18: "16", 19: "other"}),
        "fault kind before schedule syntax": _words({19: "other", 20: "x"}),
        "schedule before contract": _words({1: "0", 20: "1"}),
        "fault cycle in no run": _words({1: "0", 19: "drop", 20: "0", 21: "1"}),
        "contract before invariants": _words({2: "0", 3: "-1"}),
    }


def _outcome(content: bytes) -> dict[str, Any]:
    """Read one configuration and return the run or the refusal.

    Parameters
    ----------
    content
        Configuration bytes.

    Returns
    -------
    dict[str, Any]
        ``{"run": ...}`` or ``{"refusal": text}``.
    """
    try:
        run = read_amp_run(content)
    except ValueError as error:
        return {"refusal": str(error)}
    return {"run": {**asdict(run), "coefficients": list(run.coefficients)}}


def corpus() -> dict[str, Any]:
    """Read every case and return the corpus.

    Returns
    -------
    dict[str, Any]
        The cases with their outcomes.
    """
    cases: dict[str, bytes] = {}
    for group in (_layout_cases, _syntax_cases, _bound_cases, _schedule_cases, _contract_cases):
        cases |= group()
    cases |= _order_cases()
    return {
        "schema": "loop-timing-witness.amp-run-input-cases.v1",
        "description": (
            "Python's read_amp_run on the ISA image's configuration, changed per case. content is "
            "Latin-1 text, one character per byte; run is dataclasses.asdict of the result with "
            "the coefficients as a list, refusal Python's text."
        ),
        "cases": [
            {"name": name, "content": content.decode("latin-1"), **_outcome(content)}
            for name, content in cases.items()
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
    """Rebuild the corpus with Python's reader and require the committed file."""
    assert LONGEST * UINT32_MAX <= MAX_DURATION_TICKS < (LONGEST + 1) * UINT32_MAX
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus())
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
