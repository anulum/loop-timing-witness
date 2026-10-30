# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete integer-only original receipt decoding

"""Decode original native completion and capture receipts through the public codec."""

from __future__ import annotations

import hashlib
import json

import pytest

from loop_timing_witness.manifest_io import JsonInputRefusalError
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_receipt_io import (
    FLAG,
    TEXT,
    UNSIGNED,
    decode_actual_receipt,
)

_COMPLETION = (
    b'{"requested_steps":1000,"observed_states":1000,"raw_spike_rows":1000,'
    b'"raw_spikes":54,"service_packets":54,"simultaneous_spike_and_pending":0,'
    b'"tail_checked_after_edge_tick":1023,"counter_at_tail_check":1024,"final_counter":2039,'
    b'"pending_empty":true,"service_quiescent":true,"pipeline_quiescent":true,'
    b'"drain_complete":true}\n'
)
_COUNTS = (
    b'{"schema_id":"loop-timing-witness.neural-capture-counts.v1","drop_counter_bits":32,'
    b'"channels":[{"role":"input","attempts":1002,"accepted":1002,"dropped":0,'
    b'"drained":1002,"overflowed":false},{"role":"state","attempts":1002,"accepted":1002,'
    b'"dropped":0,"drained":1002,"overflowed":false},{"role":"service","attempts":56,'
    b'"accepted":56,"dropped":0,"drained":56,"overflowed":false}]}\n'
)
_COMPLETION_FIELDS: dict[str, object] = {
    **dict.fromkeys(
        (
            "requested_steps",
            "observed_states",
            "raw_spike_rows",
            "raw_spikes",
            "service_packets",
            "simultaneous_spike_and_pending",
            "tail_checked_after_edge_tick",
            "counter_at_tail_check",
            "final_counter",
        ),
        UNSIGNED,
    ),
    **dict.fromkeys(
        ("pending_empty", "service_quiescent", "pipeline_quiescent", "drain_complete"), FLAG
    ),
}
_ROW_FIELDS: dict[str, object] = {
    "role": TEXT,
    **dict.fromkeys(("attempts", "accepted", "dropped", "drained"), UNSIGNED),
    "overflowed": FLAG,
}
_COUNT_FIELDS: dict[str, object] = {
    "schema_id": TEXT,
    "drop_counter_bits": UNSIGNED,
    "channels": {
        "type": "array",
        "minItems": 3,
        "maxItems": 3,
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": _ROW_FIELDS,
            "required": list(_ROW_FIELDS),
        },
    },
}


def test_original_complete_native_receipts_retain_exact_values() -> None:
    """Decode the exact original 1,000-step producer and RTL counter receipts."""
    assert hashlib.sha256(_COMPLETION).hexdigest() == (
        "f828039856537beb413abbd6c8a1e1a94c52faa9289977ccd59dedf929b3d674"
    )
    assert hashlib.sha256(_COUNTS).hexdigest() == (
        "853fd77704fd3fa4fa439e4506462068ea3b09627568b751dea70d746a928b2a"
    )
    completion = decode_actual_receipt(_COMPLETION, "producer completion", _COMPLETION_FIELDS)
    counts = decode_actual_receipt(_COUNTS, "capture counts", _COUNT_FIELDS)
    assert completion["requested_steps"] == completion["observed_states"] == 1000
    assert completion["raw_spikes"] == completion["service_packets"] == 54
    assert completion["final_counter"] == 2039
    assert completion["drain_complete"] is True
    assert [row["attempts"] for row in counts["channels"]] == [1002, 1002, 56]
    assert all(row["overflowed"] is False for row in counts["channels"])


@pytest.mark.parametrize("value", [True, 1000.0, -1, 65536, "1000", None])
def test_original_integer_fields_refuse_aliases_and_out_of_range_values(value: object) -> None:
    """Preserve integer wire encoding, including JSON Schema's integral-float edge.

    Parameters
    ----------
    value
        Actual replacement for an integer in the otherwise complete original receipt.
    """
    receipt = decode_actual_receipt(_COMPLETION, "producer completion", _COMPLETION_FIELDS)
    receipt["requested_steps"] = value
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid complete actual receipt"):
        decode_actual_receipt(json.dumps(receipt).encode(), "completion", _COMPLETION_FIELDS)


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_original_boolean_flags_require_json_boolean_encoding(value: object) -> None:
    """Refuse numeric or string aliases for the actual producer drain flag.

    Parameters
    ----------
    value
        Nonboolean replacement for the original true finalisation flag.
    """
    receipt = decode_actual_receipt(_COMPLETION, "producer completion", _COMPLETION_FIELDS)
    receipt["drain_complete"] = value
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid complete actual receipt"):
        decode_actual_receipt(json.dumps(receipt).encode(), "completion", _COMPLETION_FIELDS)


@pytest.mark.parametrize("value", [1002.0, True, -1])
def test_original_nested_channel_counts_retain_exact_integer_types(value: object) -> None:
    """Apply the strict wire-number rule inside the actual three-channel array.

    Parameters
    ----------
    value
        Replacement for a real channel's captured acceptance count.
    """
    receipt = decode_actual_receipt(_COUNTS, "capture counts", _COUNT_FIELDS)
    receipt["channels"][0]["accepted"] = value
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid complete actual receipt"):
        decode_actual_receipt(json.dumps(receipt).encode(), "capture counts", _COUNT_FIELDS)


@pytest.mark.parametrize("damage", ["extra", "missing", "row-extra", "row-missing", "array"])
def test_complete_root_and_nested_receipt_roles_remain_closed(damage: str) -> None:
    """Refuse incomplete or extended originals at both object levels.

    Parameters
    ----------
    damage
        Actual field or container change to the recorded counter receipt.
    """
    receipt = decode_actual_receipt(_COUNTS, "capture counts", _COUNT_FIELDS)
    if damage == "extra":
        receipt["unrecorded"] = 0
    elif damage == "missing":
        del receipt["drop_counter_bits"]
    elif damage == "row-extra":
        receipt["channels"][0]["unrecorded"] = 0
    elif damage == "row-missing":
        del receipt["channels"][0]["accepted"]
    else:
        receipt["channels"] = {}
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid complete actual receipt"):
        decode_actual_receipt(json.dumps(receipt).encode(), "capture counts", _COUNT_FIELDS)


@pytest.mark.parametrize("raw", [b"", b"{", b"null", b"[]", b'{"n":1,"n":2}', b'{"n":NaN}'])
def test_uninterpretable_receipt_bytes_keep_the_authored_json_refusal(raw: bytes) -> None:
    """Refuse malformed roots, duplicate fields and nonstandard numeric tokens.

    Parameters
    ----------
    raw
        Actual malformed complete receipt input bytes.
    """
    with pytest.raises(JsonInputRefusalError):
        decode_actual_receipt(raw, "producer completion", _COMPLETION_FIELDS)
