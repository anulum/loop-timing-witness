# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original declaration integer-zero parity

"""Keep JSON integer spelling distinct from decimal, exponent and string tokens."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_manifest import decode_neural_manifest


@pytest.fixture
def original_manifest() -> bytes:
    """Return the complete original carrier without its acquisition files.

    Returns
    -------
    bytes
        Exact recorded declaration for independent grammar validation.
    """
    raw = (Path(__file__).parent / "data/neural-selected-original.run.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "3a982fb1aa66f64135ce622c68e408c6dcefb78022cc270f2ecc7fd047a3b075"
    )
    assert raw.count(b'"epoch": 0') == 1
    return raw


@pytest.mark.parametrize("token", [b"0", b"-0", b" -0 ", b"\t-0\r\n"])
def test_complete_integer_zero_spellings_preserve_the_original_value(
    original_manifest: bytes, token: bytes
) -> None:
    """Read integer-zero spellings from the complete original declaration.

    Parameters
    ----------
    original_manifest
        Unmodified recorded carrier bytes.
    token
        Integer token with optional JSON whitespace and minus sign.
    """
    raw = original_manifest.replace(b'"epoch": 0', b'"epoch": ' + token, 1)
    decoded = decode_neural_manifest(raw)
    assert decoded["epoch"] == 0
    assert type(decoded["epoch"]) is int
    assert decoded == decode_neural_manifest(original_manifest)


@pytest.mark.parametrize(
    "token",
    [b"0.0", b"-0.0", b"0e0", b"-0e0", b"1e-0", b"-1", b"true", b"--0", b"-00", b"-0x", b"+0"],
)
def test_decimal_exponent_boolean_and_malformed_integer_aliases_refuse(
    original_manifest: bytes, token: bytes
) -> None:
    """Reject other wire types and invalid numeric grammar in integer fields.

    Parameters
    ----------
    original_manifest
        Complete actual carrier except for one explicit token change.
    token
        Decimal, exponent, boolean, negative or malformed count spelling.
    """
    raw = original_manifest.replace(b'"epoch": 0', b'"epoch": ' + token, 1)
    with pytest.raises(NeuralCaptureRefusalError):
        decode_neural_manifest(raw)


@pytest.mark.parametrize("token", [b"0", b"-0"])
def test_string_escapes_and_integer_tokens_have_independent_meanings(
    original_manifest: bytes, token: bytes
) -> None:
    """Retain numeric text and escaped ASCII characters inside a valid label.

    Parameters
    ----------
    original_manifest
        Recorded declaration whose run label is supplied by the reader's caller.
    token
        Zero representation independent of the string contents.
    """
    value = decode_neural_manifest(original_manifest)
    text = "literal-0"
    value["run_id"] = text
    raw = json.dumps(value).encode().replace(b'"literal-0"', rb'"\u006citeral-0"')
    raw = raw.replace(b'"epoch": 0', b'"epoch": ' + token, 1)
    parsed = decode_neural_manifest(raw)
    assert parsed["run_id"] == text
    assert parsed["epoch"] == 0
    for invalid in ['literal-0"x', "literal-0\\x"]:
        value["run_id"] = invalid
        with pytest.raises(NeuralCaptureRefusalError):
            decode_neural_manifest(json.dumps(value).encode())


@pytest.mark.parametrize("tokens", [b'"epoch": -0, "epoch": 0', b'"epoch": 0, "epoch": -0'])
def test_integer_spellings_do_not_erase_duplicate_fields(
    original_manifest: bytes, tokens: bytes
) -> None:
    """Refuse duplicate-field orders regardless of equivalent integer values.

    Parameters
    ----------
    original_manifest
        Complete recorded root with a deliberately duplicated epoch field.
    tokens
        Two-field replacement retaining both field spellings.
    """
    raw = original_manifest.replace(b'"epoch": 0', tokens, 1)
    with pytest.raises(NeuralCaptureRefusalError):
        decode_neural_manifest(raw)
