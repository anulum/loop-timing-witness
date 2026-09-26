# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict JSON input and atomic output primitives

"""Strict JSON reading and atomic artefact writing for the repository tools.

Every loader rejects repeated member names and non-object top levels, so an
edit can never silently shadow an earlier field. Canonical serialisation is
deterministic (sorted keys, two-space indentation, no non-finite numbers,
trailing newline) so generated artefacts are byte-stable and drift-checkable.
Writes replace the destination atomically, so an interrupted write never
leaves a truncated artefact behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one JSON object while rejecting repeated member names.

    Parameters
    ----------
    pairs
        Decoded ``(name, value)`` members in document order.

    Returns
    -------
    dict[str, Any]
        The object with every member name unique.

    Raises
    ------
    ValueError
        If a member name occurs more than once.
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            message = f"duplicate JSON key: {key}"
            raise ValueError(message)
        result[key] = value
    return result


def parse_json_object(raw: bytes, source: str) -> dict[str, Any]:
    """Decode hash-bound UTF-8 JSON whose top level must be an object.

    Parameters
    ----------
    raw
        Complete bytes already read from one source.
    source
        Source label for refusal messages.

    Returns
    -------
    dict[str, Any]
        The decoded top-level object.

    Raises
    ------
    ValueError
        If the bytes are not UTF-8, the document is not valid JSON, a member
        name repeats inside one object, or the top level is not an object.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = f"{source}: not UTF-8: {exc}"
        raise ValueError(message) from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        message = f"{source}: invalid JSON: {exc}"
        raise ValueError(message) from exc
    except ValueError as exc:
        message = f"{source}: {exc}"
        raise ValueError(message) from exc
    if not isinstance(value, dict):
        message = f"{source}: top-level JSON value must be an object"
        raise ValueError(message)
    return value


def load_json_object(path: Path) -> dict[str, Any]:
    """Read a strict JSON object from a filesystem path.

    Parameters
    ----------
    path
        File to read.

    Returns
    -------
    dict[str, Any]
        Decoded top-level object.

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If the bytes violate the strict JSON contract.
    """
    return parse_json_object(path.read_bytes(), str(path))


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    """Serialise one object deterministically for drift-checked artefacts.

    Parameters
    ----------
    value
        Object to serialise.

    Returns
    -------
    bytes
        UTF-8 JSON with sorted keys, two-space indentation and a trailing
        newline.

    Raises
    ------
    ValueError
        If the object contains a NaN or infinite number.
    """
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def sha256_of_file(path: Path) -> str:
    """Return the lowercase hexadecimal SHA-256 digest of one file.

    Parameters
    ----------
    path
        File to digest.

    Returns
    -------
    str
        Sixty-four lowercase hexadecimal characters.

    Raises
    ------
    OSError
        If the file cannot be read.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Replace one file with new bytes in a single atomic rename.

    The bytes go to a temporary file in the destination directory, are
    flushed to stable storage, and replace the destination with
    :func:`os.replace`. A failure before the rename leaves the previous file
    untouched and removes the temporary file.

    Parameters
    ----------
    path
        Destination file; its parent directory must exist.
    data
        Complete new content.

    Raises
    ------
    OSError
        If the temporary file cannot be written or the rename fails.
    """
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
