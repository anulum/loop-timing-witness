# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — closed JSON shapes shared with the native verifier

"""Tell whether decoded JSON has a closed shape, as the native decoder reads it.

The native verifier decodes these documents into closed typed records: every
field is required, no other field is accepted, text is text, and counts are
unsigned 64-bit integers. These predicates apply the same rules so both
languages refuse the same documents with the same message.
"""

from __future__ import annotations

from typing import Any, Final

_U64: Final = 2**64

EXECUTION_FIELDS: Final[dict[str, type]] = {
    "profile": str,
    "address_space_bytes": int,
    "cpu_seconds": int,
    "wall_seconds": int,
    "file_bytes": int,
    "python_site_initialisation": bool,
    "bytecode_writes": bool,
    "bytecode_reads": str,
}
REFERENCE_FIELDS: Final[dict[str, type]] = {"path": str, "sha256": str, "byte_length": int}


def typed(value: object, kind: type) -> bool:
    """Tell whether one value has the exact closed type.

    Parameters
    ----------
    value
        Decoded JSON value.
    kind
        ``str``, ``bool`` or ``int`` (an unsigned 64-bit integer).

    Returns
    -------
    bool
        Whether the value has that type and range.
    """
    if kind is int:
        return type(value) is int and 0 <= value < _U64
    return type(value) is kind


def record(value: object, fields: dict[str, type]) -> bool:
    """Tell whether one value holds exactly the typed fields.

    Parameters
    ----------
    value
        Decoded JSON value.
    fields
        Field names with their closed types.

    Returns
    -------
    bool
        Whether every field is present and typed and nothing else is declared.
    """
    return (
        isinstance(value, dict)
        and set(value) == set(fields)
        and all(typed(value[name], kind) for name, kind in fields.items())
    )


def records(value: object, fields: dict[str, type]) -> bool:
    """Tell whether one value is a list of closed typed records.

    Parameters
    ----------
    value
        Decoded JSON value.
    fields
        Field names with their closed types.

    Returns
    -------
    bool
        Whether every item is such a record.
    """
    return isinstance(value, list) and all(record(item, fields) for item in value)


def texts(value: object) -> bool:
    """Tell whether one value is a list of text.

    Parameters
    ----------
    value
        Decoded JSON value.

    Returns
    -------
    bool
        Whether every item is text.
    """
    return isinstance(value, list) and all(type(item) is str for item in value)


def checker_policy_closed(value: dict[str, Any]) -> bool:
    """Tell whether a checker policy has the complete closed typed form.

    Parameters
    ----------
    value
        Decoded checker policy.

    Returns
    -------
    bool
        Whether every field is present and typed and nothing else is declared.
    """
    return (
        set(value)
        == {
            "schema_id",
            "entry_point",
            "source_files",
            "runtime_contract_ref",
            "generate_arguments",
            "check_arguments",
            "execution_contract",
        }
        and typed(value["schema_id"], str)
        and record(value["entry_point"], REFERENCE_FIELDS)
        and records(value["source_files"], REFERENCE_FIELDS)
        and record(value["runtime_contract_ref"], REFERENCE_FIELDS)
        and texts(value["generate_arguments"])
        and texts(value["check_arguments"])
        and record(value["execution_contract"], EXECUTION_FIELDS)
    )
