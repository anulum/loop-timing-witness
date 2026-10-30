# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural run observations

"""Decode complete strict integer-only source receipts."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .manifest_io import parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError

UNSIGNED = {"type": "integer", "minimum": 0, "maximum": 65535}
TEXT = {"type": "string"}
FLAG = {"type": "boolean"}
FILE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "path": TEXT,
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "byte_length": UNSIGNED,
    },
    "required": ["path", "sha256", "byte_length"],
}


def _exact_integer_numbers(value: object) -> bool:
    """Reject decimal number encodings throughout integer-only actual receipts.

    Parameters
    ----------
    value
        Original decoded complete JSON receipt tree.

    Returns
    -------
    bool
        True when no decimal encoding occurs. Field schema validation separately
        requires boolean flags and refuses booleans in integer count positions.
    """
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(_exact_integer_numbers(child) for child in value.values())
    if isinstance(value, list):
        return all(_exact_integer_numbers(child) for child in value)
    return True


def decode_actual_receipt(raw: bytes, name: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Decode a strict receipt and require its complete closed original structure.

    Parameters
    ----------
    raw
        Complete original already bound receipt bytes.
    name
        Semantic original receipt name.
    fields
        Complete expected field schemas for this source-owned draft.

    Returns
    -------
    dict[str, Any]
        Admitted original declarations.

    Raises
    ------
    ValueError
        If JSON or any original receipt shape is uninterpretable.
    """
    value = parse_json_object(raw, name)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": fields,
        "required": list(fields),
    }
    if not _exact_integer_numbers(value) or list(Draft202012Validator(schema).iter_errors(value)):
        message = f"Invalid complete actual receipt: {name}."
        raise NeuralCaptureRefusalError(message)
    return value
