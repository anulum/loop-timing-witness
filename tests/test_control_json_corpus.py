# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared bounded JSON corpus of the control-run analysis

r"""Keep the bounded-JSON corpus that both analysis implementations must reproduce.

Every case is raw document bytes with either the decoded object or the exact
refusal of :func:`parse_bounded_json_object`, and the outcome of
:func:`parse_dispatch_json_object`: whether the document selects the neural
analysis, or its refusal. Refusals are kept as standard error prints them,
with ``\udXXX`` for an unpaired surrogate. The cases cover the refusal
classes and, where a document has several defects, which one Python reports
first. The native crate's unit tests read the same committed file.
"""

from __future__ import annotations

import json
from typing import Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import (
    MAX_BOUNDED_DEPTH,
    JsonInputRefusalError,
    nesting_depth,
    parse_bounded_json_object,
    parse_dispatch_json_object,
)

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-json-cases.json"
SOURCE: Final = "document"


def _documents() -> list[bytes]:
    """Return every raw document of the corpus.

    Returns
    -------
    list[bytes]
        Valid and refused documents.
    """
    deep = MAX_BOUNDED_DEPTH
    texts = [
        '{"a": 1}',
        "{}",
        '{"a": {}, "b": [], "c": { }, "d": [ ]}',
        ' \t\n\r{"a": [1, 2.5, -0, -0.0, 1e5, 1E-5, 1.5e+3, 0e400, 1e-999, true, false, null]}\r\n',
        '{"text": "\\u00e9\\/\\"\\\\\\b\\f\\n\\r\\t", "pair": "\\ud83d\\ude00"}',
        '{"\\ud834\\udd1e": 1}',
        '{"precise": 0.1000000000000000055511151231257827, "tiny": 5e-324}',
        '{"big": 1.7976931348623157e308}',
        '{"bounds": [-9223372036854775808, 18446744073709551615, 9223372036854775807]}',
        '{"low": -9223372036854775809}',
        '{"high": 18446744073709551616}',
        '{"long": 000000000000000000001}',
        '{"wide": 123456789012345678901}',
        '{"negative wide": -000000000000000000001}',
        '{"overflow": 1e999}',
        '{"overflow": -1e400}',
        '{"value": NaN}',
        '{"value": Infinity}',
        '{"value": -Infinity}',
        '{"value": nan}',
        '{"value": +1}',
        '{"value": .5}',
        '{"value": 1.}',
        '{"value": 1e}',
        '{"value": -}',
        '{"value": 01}',
        '{"value": -01}',
        '{"value": t}',
        '{"value": "\\x"}',
        '{"value": "\\u12"}',
        '{"value": "line\nbreak"}',
        '{"value": "unterminated}',
        '{"value": 1,}',
        '{"value" 1}',
        '{"value": 1} extra',
        "{1: 2}",
        "{NaN: 1}",
        '{"value": [1, 2,]}',
        '{"value": \u00a01}',
        "",
        "   ",
        "[]",
        '"text"',
        "1",
        "null",
        '{"a": 1, "a": 2}',
        '{"a": 1, "a": 2, "c": {"d": 1, "d": 1}}',
        '{"a": 1, "a": 2, "b": NaN}',
        '{"a": 1, "a": 2, "b": 1e999, "c": 18446744073709551616}',
        '{"a": [1, {"b": 1, "b": 2}], "x": 1, "x": 2}',
        '{"\\ud800": 1, "x": 1, "x": 2}',
        '{"key": "\\ud800"}',
        '{"\\udc00": 1}',
        '{"key": "\\udc00\\ud800"}',
        '{"key": "\\ud800"} extra',
        '{"key": "\\ud800", "n": NaN}',
        '{"key": ["\\ud83d\\ude00"]}',
        '{"key": "\\uD83D\\uDE00"}',
        '{"\\ud800": 1, "\\ud800": 2}',
        '{"\\ud800": 1, "\\ud801": 2}',
        '{"\\ud800": 1, "\\\\ud800": 2}',
        '{"\\ud800": 1, "\\ufffd": 2}',
        '{"a\\ud800b\\n": 1, "a\\ud800b\\n": 2}',
        '{"schema_id": 1, "big": 18446744073709551616}',
        '{"schema_id": "\\ud800"}',
        '{"n": ' + "9" * 5000 + "}",
        '{"schema_id": 1, "x": ' + "[" * deep + "]" * deep + "}",
        "[" * deep + "]" * deep,
        '{"a":' * (deep - 1) + "[]" + "}" * (deep - 1),
        "[" * (deep + 1) + "]" * (deep + 1),
        "[" * (deep + 1),
        '{"text": "' + "[" * 100 + '"}',
        '{"text": "\\"' + "{" * 100 + '"}',
        '{"text": "\\\\"' + "[" * 100,
        '{"a": "\\\\\\"[[[[["}',
    ]
    return [
        *(text.encode("utf-8") for text in texts),
        b'{"a": "\xff"}',
        b"\xef\xbb\xbf{}",
        b'{"a": "\xed\xa0\x80"}',
        b'{"a": 1}\x00',
    ]


def _printed(error: JsonInputRefusalError) -> str:
    """Return a refusal as standard error prints it.

    Parameters
    ----------
    error
        Raised refusal.

    Returns
    -------
    str
        Text with unpaired surrogates as backslash escapes.
    """
    return str(error).encode("utf-8", "backslashreplace").decode("utf-8")


def _dispatch(raw: bytes) -> dict[str, Any]:
    """Return which analysis one document selects, or its dispatch refusal.

    Parameters
    ----------
    raw
        Document bytes.

    Returns
    -------
    dict[str, Any]
        ``neural`` or ``refusal``.
    """
    try:
        manifest = parse_dispatch_json_object(raw, SOURCE)
    except JsonInputRefusalError as error:
        return {"refusal": _printed(error)}
    return {"neural": "schema_id" in manifest}


def _outcome(raw: bytes) -> dict[str, Any]:
    """Return the decoded object or the exact refusal of one document.

    Parameters
    ----------
    raw
        Document bytes.

    Returns
    -------
    dict[str, Any]
        ``raw_hex`` and ``dispatch`` with either ``value`` or ``refusal``.
    """
    case: dict[str, Any] = {"raw_hex": raw.hex(), "dispatch": _dispatch(raw)}
    try:
        case["value"] = parse_bounded_json_object(raw, SOURCE)
    except JsonInputRefusalError as error:
        case["refusal"] = _printed(error)
    return case


def corpus() -> dict[str, Any]:
    """Build the complete bounded-JSON corpus.

    Returns
    -------
    dict[str, Any]
        Source label and cases.
    """
    return {
        "schema": "loop-timing-witness.control-json-cases.v2",
        "source": SOURCE,
        "cases": [_outcome(raw) for raw in _documents()],
    }


def test_committed_corpus_equals_python_outcomes() -> None:
    """The committed corpus is exactly what Python decodes or refuses."""
    expected = json.dumps(corpus(), ensure_ascii=True, indent=1, sort_keys=True) + "\n"
    assert CORPUS.read_text(encoding="utf-8") == expected


def test_corpus_covers_every_refusal_class_and_precedence() -> None:
    """Hold each refusal class and the documented precedence between defects."""
    outcomes = {bytes.fromhex(case["raw_hex"]): case for case in corpus()["cases"]}
    refusals = {case.get("refusal", "") for case in outcomes.values()}
    for text in (
        "not UTF-8",
        "invalid JSON",
        "duplicate JSON key: a",
        "non-finite JSON number: NaN",
        "non-finite JSON number: 1e999",
        "integer outside the 64-bit range: 18446744073709551616",
        "JSON text holds an unpaired surrogate escape",
        "JSON input exceeds decoder limits",
        "top-level JSON value must be an object",
    ):
        assert f"{SOURCE}: {text}" in refusals, text
    expectations = {
        b'{"a": 1, "a": 2, "c": {"d": 1, "d": 1}}': "duplicate JSON key: d",
        b'{"a": 1, "a": 2, "b": NaN}': "non-finite JSON number: NaN",
        b'{"\\ud800": 1, "x": 1, "x": 2}': "duplicate JSON key: x",
        b'{"key": "\\ud800"} extra': "invalid JSON",
        b'{"key": "\\ud800", "n": NaN}': "non-finite JSON number: NaN",
        b"[" * (MAX_BOUNDED_DEPTH + 1): "JSON input exceeds decoder limits",
        b'{"\\ud800": 1, "\\ud800": 2}': "duplicate JSON key: \\ud800",
        b'{"\\ud800": 1, "\\ud801": 2}': "JSON text holds an unpaired surrogate escape",
        b'{"\\ud800": 1, "\\\\ud800": 2}': "JSON text holds an unpaired surrogate escape",
        b'{"a\\ud800b\\n": 1, "a\\ud800b\\n": 2}': "duplicate JSON key: a\\ud800b\n",
    }
    for raw, text in expectations.items():
        assert outcomes[raw]["refusal"] == f"{SOURCE}: {text}"
    dispatch = {
        b'{"schema_id": 1, "big": 18446744073709551616}': {"neural": True},
        b'{"schema_id": "\\ud800"}': {"neural": True},
        b'{"n": ' + b"9" * 5000 + b"}": {"neural": False},
        b'{"\\ud800": 1, "\\ud800": 2}': {"refusal": f"{SOURCE}: duplicate JSON key: \\ud800"},
        b"[" * (MAX_BOUNDED_DEPTH + 1): {"refusal": f"{SOURCE}: JSON input exceeds decoder limits"},
    }
    for raw, outcome in dispatch.items():
        assert outcomes[raw]["dispatch"] == outcome
    assert outcomes[b"[" * MAX_BOUNDED_DEPTH + b"]" * MAX_BOUNDED_DEPTH]["refusal"] == (
        f"{SOURCE}: top-level JSON value must be an object"
    )
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_nesting_depth_ignores_brackets_inside_strings() -> None:
    """Count only structural brackets, honouring escaped quotes and backslashes."""
    assert nesting_depth('[{"a": "[[{{"}]') == 2
    assert nesting_depth('["\\"[[", "\\\\", [1]]') == 2
    assert nesting_depth("]]][") == 0
    assert nesting_depth("") == 0
