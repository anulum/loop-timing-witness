# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capture, counter and trace-row faults of a hermetic acquisition

"""Damage one capture record, counter or trace row and require one outcome in both languages.

Each fault is either a refusal of the whole acquisition or a finding of the
capture dimension; Python and Rust must give the same refusal or report.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any

import pytest
from neural_acquisition_support import build_neural_acquisition, edit_json, make_writable
from neural_rust_support import assert_same_outcome, python_outcome, rust_outcome

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from neural_acquisition_support import Change

_MARKER = 17
_SATURATED = 2**32 - 1


def _records(raw: bytes) -> list[bytearray]:
    """Split a capture into its 16-byte records.

    Parameters
    ----------
    raw
        Complete capture bytes.

    Returns
    -------
    list[bytearray]
        Mutable records in capture order.
    """
    return [bytearray(raw[offset : offset + 16]) for offset in range(0, len(raw), 16)]


def _identity(record: bytearray, value: int) -> None:
    """Set the identity field of one record.

    Parameters
    ----------
    record
        Mutable 16-byte record.
    value
        Assigned identity.
    """
    struct.pack_into("<I", record, 4, value)


def _tick(record: bytearray, value: int) -> None:
    """Set the tick field of one record.

    Parameters
    ----------
    record
        Mutable 16-byte record.
    value
        Assigned tick.
    """
    struct.pack_into("<Q", record, 8, value)


def _capture(
    index: int, edit: Callable[[list[bytearray]], None], *, project: bool = True
) -> Change:
    """Return a change of one channel capture, optionally keeping its projections.

    Parameters
    ----------
    index
        Channel index: 0 input, 1 state, 2 service.
    edit
        Mutates the record list in place.
    project
        Rewrite the payload and marker projections from the changed capture.

    Returns
    -------
    Change
        Capture rewrite.
    """
    target = f"channel-{index}.bin"
    projected: dict[str, bytes] = {}

    def change(name: str, raw: bytes) -> bytes:
        """Rewrite the capture and, when projecting, both projection files.

        Parameters
        ----------
        name, raw
            File path and original bytes.

        Returns
        -------
        bytes
            Rewritten bytes, or the original bytes.
        """
        if name == target:
            records = _records(raw)
            edit(records)
            projected[f"payload-{index}.bin"] = b"".join(r for r in records if r[0] != _MARKER)
            projected[f"markers-{index}.bin"] = b"".join(r for r in records if r[0] == _MARKER)
            return b"".join(records)
        if project and name in projected:
            return projected[name]
        return raw

    return change


def _bytes(target: str, edit: Callable[[bytearray], None]) -> Change:
    """Return a change of one binary file's bytes.

    Parameters
    ----------
    target
        Within-run path.
    edit
        Mutates the bytes in place.

    Returns
    -------
    Change
        Byte rewrite.
    """

    def change(name: str, raw: bytes) -> bytes:
        """Rewrite the target only.

        Parameters
        ----------
        name, raw
            File path and original bytes.

        Returns
        -------
        bytes
            Rewritten bytes, or the original bytes.
        """
        if name != target:
            return raw
        data = bytearray(raw)
        edit(data)
        return bytes(data)

    return change


def _counts(role: int, **fields: object) -> Change:
    """Return a change of one channel's counter receipt fields.

    Parameters
    ----------
    role
        Channel index.
    **fields
        Assigned counter fields.

    Returns
    -------
    Change
        Counter receipt rewrite.
    """
    return edit_json("capture-counts.json", lambda value: value["channels"][role].update(fields))


def _row(target: str, edit: Callable[[bytes], bytes]) -> Change:
    """Return a change of one trace file's whole bytes.

    Parameters
    ----------
    target
        Within-run trace path.
    edit
        Returns the rewritten trace.

    Returns
    -------
    Change
        Trace rewrite.
    """
    return lambda name, raw: edit(raw) if name == target else raw


def _first_field(value: bytes) -> Callable[[bytes], bytes]:
    """Return an edit that replaces the last field of the first input row.

    Parameters
    ----------
    value
        Replacement field bytes.

    Returns
    -------
    Callable[[bytes], bytes]
        Trace edit.
    """

    def edit(raw: bytes) -> bytes:
        """Replace the field.

        Parameters
        ----------
        raw
            Original trace.

        Returns
        -------
        bytes
            Edited trace.
        """
        first, rest = raw.split(b"\n", 1)
        fields = first.split(b" ")
        fields[-1] = value
        return b" ".join(fields) + b"\n" + rest

    return edit


def _set(index: int, field: Callable[[bytearray, int], None], value: int) -> Callable[..., None]:
    """Return a record-list edit assigning one field of one record.

    Parameters
    ----------
    index
        Record index.
    field
        Field setter.
    value
        Assigned value.

    Returns
    -------
    Callable[..., None]
        Record-list edit.
    """
    return lambda records: field(records[index], value)


def _marker_at(index: int, identity: int) -> Callable[[list[bytearray]], None]:
    """Return an edit turning one data record into a marker with an identity.

    Parameters
    ----------
    index
        Record index.
    identity
        Marker identity.

    Returns
    -------
    Callable[[list[bytearray]], None]
        Record-list edit.
    """

    def edit(records: list[bytearray]) -> None:
        """Relabel the record.

        Parameters
        ----------
        records
            Mutable records.
        """
        records[index][0] = _MARKER
        _identity(records[index], identity)

    return edit


def _reserved(records: list[bytearray]) -> None:
    """Set a reserved byte of the first data record.

    Parameters
    ----------
    records
        Mutable records.
    """
    records[1][1] = 1


def _code(records: list[bytearray]) -> None:
    """Give the first input data record the state event code.

    Parameters
    ----------
    records
        Mutable records.
    """
    records[1][0] = 15


def _repeat_tick(records: list[bytearray]) -> None:
    """Give the second data record the tick of the first.

    Parameters
    ----------
    records
        Mutable records.
    """
    records[2][8:] = records[1][8:]


def _repeat_identity(records: list[bytearray]) -> None:
    """Give the second data record the identity of the first.

    Parameters
    ----------
    records
        Mutable records.
    """
    records[2][4:8] = records[1][4:8]


def _remove(index: int) -> Callable[[list[bytearray]], None]:
    """Return an edit removing one record.

    Parameters
    ----------
    index
        Record index.

    Returns
    -------
    Callable[[list[bytearray]], None]
        Record-list edit.
    """

    def edit(records: list[bytearray]) -> None:
        """Remove the record.

        Parameters
        ----------
        records
            Mutable records.
        """
        del records[index]

    return edit


def _truncate(data: bytearray) -> None:
    """Remove the last byte of a capture.

    Parameters
    ----------
    data
        Mutable bytes.
    """
    del data[-1]


def _flip(data: bytearray) -> None:
    """Change the last byte of a projection.

    Parameters
    ----------
    data
        Mutable bytes.
    """
    data[-1] ^= 1


_CASES: dict[str, tuple[Change, str, str]] = {
    "capture-incomplete": (
        _bytes("channel-0.bin", _truncate),
        "refusal",
        "not a whole sequence of 16-byte records",
    ),
    "capture-reserved": (_capture(0, _reserved), "refusal", "reserved bits must be zero"),
    "capture-tick-range": (
        _capture(0, _set(1, _tick, 65536)),
        "refusal",
        "ticks regress, repeat or exceed the no-wrap horizon",
    ),
    "capture-tick-order": (
        _capture(0, _repeat_tick),
        "refusal",
        "ticks regress, repeat or exceed the no-wrap horizon",
    ),
    "capture-start-identity": (
        _capture(0, _set(0, _identity, 1)),
        "refusal",
        "alignment marker has an invalid identity or position",
    ),
    "capture-start-placement": (
        _capture(0, _marker_at(1, 0), project=False),
        "refusal",
        "alignment marker has an invalid identity or position",
    ),
    "capture-end-placement": (
        _capture(0, _marker_at(1, 1), project=False),
        "refusal",
        "alignment marker has an invalid identity or position",
    ),
    "capture-code": (_capture(0, _code), "refusal", "a code from another channel or profile"),
    "capture-identity-range": (
        _capture(0, _set(-2, _identity, 1000)),
        "refusal",
        "identities repeat, regress or exceed the population",
    ),
    "capture-identity-order": (
        _capture(0, _repeat_identity),
        "refusal",
        "identities repeat, regress or exceed the population",
    ),
    "counts-attempts-below-accepted": (
        _counts(0, attempts=1001),
        "capture",
        "input: attempted, accepted and dropped counts disagree",
    ),
    "counts-dropped": (
        _counts(0, dropped=1, overflowed=True),
        "capture",
        "input: attempted, accepted and dropped counts disagree",
    ),
    "counts-overflow-flag": (
        _counts(0, overflowed=True),
        "capture",
        "input: overflow flag and drop counter disagree",
    ),
    "counts-saturated-excess": (
        _counts(0, dropped=_SATURATED, overflowed=True),
        "capture",
        "input: drop counter is a lower bound at saturation",
    ),
    "counts-saturated-bound": (
        _counts(0, attempts=1002 + _SATURATED + 5, dropped=_SATURATED, overflowed=True),
        "capture",
        "input: drop counter is a lower bound at saturation",
    ),
    "counts-drained": (
        _counts(0, drained=1001),
        "capture",
        "input: accepted records were not completely drained",
    ),
    "projection-payload": (
        _bytes("payload-0.bin", _flip),
        "capture",
        "input: payload file differs from original capture projection",
    ),
    "projection-markers": (
        _bytes("markers-0.bin", _flip),
        "capture",
        "input: marker file differs from original capture projection",
    ),
    "capture-missing-start": (
        _capture(0, _remove(0)),
        "capture",
        "input: missing alignment marker",
    ),
    "capture-missing-end": (
        _capture(0, _remove(-1)),
        "capture",
        "input: missing alignment marker",
    ),
    "capture-end-horizon": (
        _capture(0, _set(-1, _tick, 4096)),
        "capture",
        "input: end marker exceeds capture horizon",
    ),
    "capture-step-population": (
        _capture(0, _remove(6)),
        "capture",
        "input: step population differs from requested identities",
    ),
    "capture-state-missing": (
        _capture(1, _remove(6)),
        "capture",
        "state: step population differs from requested identities",
    ),
    "capture-service-population": (
        _capture(2, _remove(6)),
        "capture",
        "service: packet population differs from requested identities",
    ),
    "trace-not-utf8": (
        _row("input.txt", _first_field(b"\xff")),
        "refusal",
        "Original input_trace trace is not ASCII",
    ),
    "trace-not-ascii": (
        _row("input.txt", _first_field("é".encode())),
        "refusal",
        "Original input_trace trace is not ASCII",
    ),
    "trace-final-newline": (
        _row("input.txt", lambda raw: raw[:-1]),
        "refusal",
        "Original input_trace trace lacks its final newline",
    ),
    "trace-columns": (
        _row("input.txt", lambda raw: raw.replace(b" ", b"", 1)),
        "refusal",
        "Malformed original input_trace trace row",
    ),
    "trace-empty-field": (
        _row("input.txt", _first_field(b"")),
        "refusal",
        "Malformed original input_trace trace row",
    ),
    "trace-sign-only": (
        _row("input.txt", _first_field(b"+")),
        "refusal",
        "Malformed original input_trace trace row",
    ),
    "trace-long-field": (
        _row("input.txt", _first_field(b"1" * 21)),
        "refusal",
        "Malformed original input_trace trace row",
    ),
    "trace-non-digit": (
        _row("input.txt", _first_field(b"1x")),
        "refusal",
        "Malformed original input_trace trace row",
    ),
    "trace-signed64": (
        _row("input.txt", _first_field(b"9223372036854775808")),
        "refusal",
        "Original input_trace trace integer outside signed64 range",
    ),
    "trace-epoch": (
        _row("input.txt", lambda raw: b"1" + raw[1:]),
        "refusal",
        "Original epoch/step sequence differs: input_trace",
    ),
    "trace-negative-tick": (
        _row("input.txt", _first_field(b"-1")),
        "refusal",
        "Original observed tick outside no-wrap horizon: input_trace",
    ),
}


@pytest.mark.parametrize("fault", list(_CASES))
def test_capture_and_trace_fault_has_one_outcome_in_both(tmp_path: Path, fault: str) -> None:
    """Require the same refusal or capture finding in both languages.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    fault
        Named single fault.
    """
    change, kind, message = _CASES[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", change=change)
    try:
        python: dict[str, Any] = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    if kind == "refusal":
        assert message in python.get("refusal", ""), python.get("refusal", python)
    else:
        findings = python["report"][kind]["findings"]
        assert any(message in finding for finding in findings), findings
        assert python["report"]["verification"]["whole"] is False
