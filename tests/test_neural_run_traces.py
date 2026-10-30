# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original neural trace row grammar

"""Require exact trace delimiters and finite integers through the public decoder."""

from __future__ import annotations

import pytest

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_traces import decode_rows


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"", []),
        (b"0 -26\n0 0\n1 0\n", [(0, -26), (0, 0), (1, 0)]),
        (b"+0 -0\n", [(0, 0)]),
        (b"00000000000000000000 1\n", [(0, 1)]),
        (b"-9223372036854775808 +9223372036854775807\n", [(-(1 << 63), (1 << 63) - 1)]),
    ],
)
def test_original_trace_fields_are_not_rewritten(
    raw: bytes, expected: list[tuple[int, ...]]
) -> None:
    """Retain original signed fields and the empty service population.

    Parameters
    ----------
    raw
        Exact original row bytes or an integer boundary control.
    expected
        Parsed values in the original order, including signed zero.
    """
    assert decode_rows(raw, 2, "numerical projection") == expected


@pytest.mark.parametrize("separator", [b"\r", b"\r\n", b"\v", b"\f", b"\x1c", b"\x1d", b"\x1e"])
def test_control_separators_do_not_replace_original_lf(separator: bytes) -> None:
    """Reject line boundaries which Python splitlines would silently normalise.

    Parameters
    ----------
    separator
        Actual replacement for the first LF of the selected trace prefix.
    """
    raw = b"0 -26\n0 0\n1 0\n".replace(b"\n", separator, 1)
    with pytest.raises(
        NeuralCaptureRefusalError, match=r"^Malformed original numerical projection trace row\.$"
    ):
        decode_rows(raw, 2, "numerical projection")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"1 2", "trace lacks its final newline"),
        (b"\xff 2\n", "trace is not ASCII"),
        ("1 \u00e9\n".encode(), "trace is not ASCII"),
        (b"1\n", "trace row"),
        (b"1 2 3\n", "trace row"),
        (b"1  2\n", "trace row"),
        (b"1\t2\n", "trace row"),
        (b"1 2\n\n", "trace row"),
        (b"1 +\n", "trace row"),
        (b"1 --2\n", "trace row"),
        (b"1 000000000000000000000\n", "trace row"),
        (b"1 9223372036854775808\n", "integer outside signed64 range"),
        (b"1 -9223372036854775809\n", "integer outside signed64 range"),
        (b"1 18446744073709551615\n", "integer outside signed64 range"),
    ],
)
def test_malformed_trace_bytes_have_authored_refusals(raw: bytes, message: str) -> None:
    """Keep grammar, encoding and integer failures within the public refusal type.

    Parameters
    ----------
    raw
        Actual malformed bytes or an integer outside the native field range.
    message
        Authored diagnostic shared with the native row reader.
    """
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        decode_rows(raw, 2, "numerical projection")
