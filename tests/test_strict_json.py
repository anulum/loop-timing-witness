# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict JSON decoding and canonical serialisation

"""Contract tests for strict and bounded JSON decoding and canonical serialisation."""

from __future__ import annotations

import math
import sys

import pytest

from loop_timing_witness.strict_json import (
    MAX_BOUNDED_DEPTH,
    JsonInputRefusalError,
    canonical_json_bytes,
    nesting_depth,
    parse_bounded_json_object,
    parse_dispatch_json_object,
    parse_json_object,
)


def test_a_well_formed_object_decodes_with_nested_values() -> None:
    """Objects, arrays, literals and non-ASCII strings decode as written."""
    raw = '{"alpha": 1, "beta": [true, null], "gamma": {"delta": "ε"}}'.encode()
    assert parse_json_object(raw, "doc") == {
        "alpha": 1,
        "beta": [True, None],
        "gamma": {"delta": "ε"},
    }


@pytest.mark.parametrize(
    ("text", "name"),
    [('{"alpha": 1, "alpha": 2}', "alpha"), ('{"outer": {"inner": 1, "inner": 2}}', "inner")],
    ids=["top level", "nested"],
)
def test_a_repeated_member_name_is_refused_at_any_depth(text: str, name: str) -> None:
    """A repeated name fails instead of silently keeping the last value, with the label.

    Parameters
    ----------
    text
        Document repeating one member name.
    name
        The repeated name.
    """
    with pytest.raises(JsonInputRefusalError) as refused:
        parse_json_object(text.encode(), "doc.json")
    assert str(refused.value) == f"doc.json: duplicate JSON key: {name}"
    assert refused.value.source == "doc.json"


@pytest.mark.parametrize(
    ("raw", "refusal"),
    [
        (b"[1, 2]", "top-level JSON value must be an object"),
        (b"{not json", "invalid JSON"),
        ('{"name": "Šotek"}'.encode("cp1250"), "not UTF-8"),
    ],
    ids=["array", "syntax", "cp1250"],
)
def test_documents_outside_the_contract_are_refused_with_the_label(
    raw: bytes, refusal: str
) -> None:
    """A non-object top level, a syntax error and non-UTF-8 bytes each have one refusal.

    Parameters
    ----------
    raw
        Refused document bytes.
    refusal
        Refusal after the label.
    """
    with pytest.raises(JsonInputRefusalError) as refused:
        parse_json_object(raw, "doc.json")
    assert str(refused.value) == f"doc.json: {refusal}"


@pytest.mark.parametrize("limit", ["integer", "nesting"])
def test_real_decoder_limits_have_an_authored_refusal(limit: str) -> None:
    """Actual integer and recursion limits refuse input without decoder diagnostics.

    Parameters
    ----------
    limit
        Decimal integer conversion or deeply nested input, with no interpreter setting changed.
    """
    if limit == "integer":
        maximum = sys.get_int_max_str_digits()
        assert maximum > 0
        text = '{"value":' + "9" * (maximum + 1) + "}"
    else:
        # CPython 3.14 and later bound decoding by the actual C stack rather than the
        # recursion limit; a million levels exceed it on every supported stack size.
        depth = 1_000_000
        text = '{"value":' + "[" * depth + "0" + "]" * depth + "}"
    with pytest.raises(JsonInputRefusalError) as refused:
        parse_json_object(text.encode(), "limits.json")
    assert str(refused.value) == "limits.json: JSON input exceeds decoder limits"
    assert isinstance(refused.value.__cause__, RecursionError if limit == "nesting" else ValueError)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
@pytest.mark.parametrize("shape", ['{"value":%s}', '{"nested":{"value":%s}}', '{"values":[%s]}'])
def test_nonfinite_numbers_are_refused_at_every_depth(token: str, shape: str) -> None:
    """Refuse a nonfinite extension or an overflowing exponent wherever it stands.

    Parameters
    ----------
    token
        Nonfinite extension or an exponent that overflows on decoding.
    shape
        Top-level field, nested object or nested array containing the number.
    """
    with pytest.raises(JsonInputRefusalError, match=r"^nonfinite\.json: non-finite JSON number"):
        parse_json_object((shape % token).encode(), "nonfinite.json")


@pytest.mark.parametrize(
    "token", ["1.25", "1.7976931348623157e308", "-1.7976931348623157e308", "1e-999"]
)
def test_finite_numbers_and_literal_strings_are_kept(token: str) -> None:
    """Retain finite numeric boundaries and ordinary strings naming rejected tokens.

    Parameters
    ----------
    token
        Representable finite decimal, maximal signed magnitude or underflow to zero.
    """
    raw = ('{"value":' + token + ',"labels":["NaN","Infinity","-Infinity"]}').encode()
    result = parse_json_object(raw, "finite.json")
    assert math.isfinite(result["value"])
    assert result["value"] == float(token)
    assert result["labels"] == ["NaN", "Infinity", "-Infinity"]


def test_nesting_depth_counts_brackets_outside_strings_only() -> None:
    """Brackets inside strings, escaped quotes included, do not count."""
    assert nesting_depth('{"a": [1, {"b": []}]}') == 4
    assert nesting_depth('{"a": "[[[{", "b": "\\"[[["}') == 1
    assert nesting_depth("[]") == 1
    assert nesting_depth('"no brackets"') == 0


def test_bounded_decoding_accepts_the_limits_themselves() -> None:
    """The deepest admitted nesting and both 64-bit integer extremes decode."""
    deepest = "[" * (MAX_BOUNDED_DEPTH - 1) + "]" * (MAX_BOUNDED_DEPTH - 1)
    raw = '{"a": ' + deepest + ', "low": -9223372036854775808, "high": 18446744073709551615}'
    value = parse_bounded_json_object(raw.encode(), "receipt.json")
    assert value["low"] == -(2**63)
    assert value["high"] == 2**64 - 1


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ('{"a": 18446744073709551616}', "integer outside the 64-bit range: 18446744073709551616"),
        ('{"a": -9223372036854775809}', "integer outside the 64-bit range: -9223372036854775809"),
        ('{"a": ' + "1" * 21 + "}", "integer outside the 64-bit range: " + "1" * 21),
        ('{"a": "\\ud800"}', "JSON text holds an unpaired surrogate escape"),
        ('{"\\udfff": 1}', "JSON text holds an unpaired surrogate escape"),
        ('{"a": ' + "[" * 64 + "]" * 64 + "}", "JSON input exceeds decoder limits"),
        ('{"a": 1, "a": 2}', "duplicate JSON key: a"),
        ("[0]", "top-level JSON value must be an object"),
        ("{", "invalid JSON"),
    ],
    ids=[
        "wide integer",
        "low integer",
        "long digits",
        "unpaired value",
        "unpaired name",
        "nesting 65",
        "repeated name",
        "array",
        "syntax",
    ],
)
def test_bounded_decoding_refuses_with_the_label_as_given(text: str, refusal: str) -> None:
    """A document outside the bounded rules is refused with its label and one reason.

    Parameters
    ----------
    text
        Document text.
    refusal
        Decoder refusal after the label.
    """
    with pytest.raises(JsonInputRefusalError) as refused:
        parse_bounded_json_object(text.encode(), "receipt.json")
    assert str(refused.value) == f"receipt.json: {refusal}"


def test_bounded_decoding_refuses_bytes_that_are_not_utf8() -> None:
    """Undecodable bytes are refused before the nesting scan."""
    with pytest.raises(JsonInputRefusalError, match=r"^receipt\.json: not UTF-8$"):
        parse_bounded_json_object(b'{"a": "\xff"}', "receipt.json")


def test_dispatch_decoding_keeps_integer_text_and_surrogates_for_the_chosen_analysis() -> None:
    """Integers stay as their decimal text and an unpaired surrogate is not refused."""
    raw = b'{"profile": "CONTROL", "n": 18446744073709551616, "s": "\\ud800"}'
    value = parse_dispatch_json_object(raw, "manifest.json")
    assert value == {"profile": "CONTROL", "n": "18446744073709551616", "s": "\ud800"}


def test_dispatch_decoding_bounds_nesting_before_decoding() -> None:
    """The nesting bound holds for the dispatch decoder as for the bounded one."""
    raw = ('{"a": ' + "[" * 64 + "]" * 64 + "}").encode()
    with pytest.raises(JsonInputRefusalError, match="JSON input exceeds decoder limits"):
        parse_dispatch_json_object(raw, "manifest.json")


def test_canonical_bytes_are_independent_of_key_order() -> None:
    """Insertion order does not change the serialised bytes; keys are sorted."""
    first = canonical_json_bytes({"beta": 2, "alpha": {"z": 1, "a": 2}})
    second = canonical_json_bytes({"alpha": {"a": 2, "z": 1}, "beta": 2})
    assert first == second
    assert first == b'{\n  "alpha": {\n    "a": 2,\n    "z": 1\n  },\n  "beta": 2\n}\n'


def test_canonical_bytes_keep_non_ascii_text() -> None:
    """Non-ASCII text is written as UTF-8, not as escape sequences."""
    assert "Šotek".encode() in canonical_json_bytes({"name": "Šotek"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_bytes_refuse_non_finite_numbers(value: float) -> None:
    """Non-finite numbers cannot enter a drift-checked artefact.

    Parameters
    ----------
    value
        NaN or an infinity.
    """
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_bytes({"value": value})
