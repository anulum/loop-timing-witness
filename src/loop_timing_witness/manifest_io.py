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
import math
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable


class JsonInputRefusalError(ValueError):
    """An intentionally authored refusal of invalid JSON input bytes or values.

    Attributes
    ----------
    source
        Label of the refused document, or empty when the decoder raised it first.
    """

    def __init__(self, message: str, source: str = "") -> None:
        """Keep the authored message and the refused document's label.

        Parameters
        ----------
        message
            Authored diagnostic.
        source
            Label of the refused document.
        """
        super().__init__(message)
        self.source = source


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
            raise JsonInputRefusalError(message)
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> NoReturn:
    """Refuse a nonfinite JSON extension before constructing an input object.

    Parameters
    ----------
    value
        ``NaN``, ``Infinity`` or ``-Infinity`` encountered by the decoder.

    Raises
    ------
    ValueError
        Always, because the token does not represent a finite JSON number.
    """
    message = f"non-finite JSON number: {value}"
    raise JsonInputRefusalError(message)


def _finite_json_float(value: str) -> float:
    """Decode one JSON decimal while refusing overflow to a nonfinite value.

    Parameters
    ----------
    value
        Decimal or exponent token supplied by the JSON decoder.

    Returns
    -------
    float
        Finite decoded value.

    Raises
    ------
    ValueError
        If the token overflows the floating-point representation.
    """
    result = float(value)
    if not math.isfinite(result):
        message = f"non-finite JSON number: {value}"
        raise JsonInputRefusalError(message)
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
    JsonInputRefusalError
        If the bytes are not UTF-8, the document is not valid JSON, a member
        name repeats inside one object, a number is nonfinite after decoding,
        or the top level is not an object.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = f"{source}: not UTF-8"
        raise JsonInputRefusalError(message, source) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
            parse_float=_finite_json_float,
        )
    except json.JSONDecodeError as exc:
        message = f"{source}: invalid JSON"
        raise JsonInputRefusalError(message, source) from exc
    except JsonInputRefusalError as exc:
        message = f"{source}: {exc}"
        raise JsonInputRefusalError(message, source) from exc
    except (RecursionError, ValueError) as exc:
        message = f"{source}: JSON input exceeds decoder limits"
        raise JsonInputRefusalError(message, source) from exc
    if not isinstance(value, dict):
        message = f"{source}: top-level JSON value must be an object"
        raise JsonInputRefusalError(message, source)
    return value


MAX_BOUNDED_DEPTH = 64
"""Deepest array or object nesting a bounded document may use."""
MAX_INTEGER_DIGITS = 20
"""Most digits of any integer within the signed and unsigned 64-bit ranges."""


def _bounded_json_int(value: str) -> int:
    """Decode one JSON integer that fits a signed or unsigned 64-bit field.

    Parameters
    ----------
    value
        Integer token supplied by the JSON decoder.

    Returns
    -------
    int
        Decoded value between -2**63 and 2**64 - 1.

    Raises
    ------
    JsonInputRefusalError
        If the value is outside that range.
    """
    if len(value.removeprefix("-")) <= MAX_INTEGER_DIGITS:
        number = int(value)
        if -(2**63) <= number <= 2**64 - 1:
            return number
    message = f"integer outside the 64-bit range: {value}"
    raise JsonInputRefusalError(message)


def nesting_depth(text: str) -> int:
    """Return the deepest bracket nesting outside JSON strings.

    The scan only counts ``[``, ``{``, ``]`` and ``}`` outside double-quoted
    strings, honouring backslash escapes; it does not validate the document.

    Parameters
    ----------
    text
        Decoded document text.

    Returns
    -------
    int
        Greatest number of simultaneously open brackets.
    """
    depth = deepest = 0
    in_string = escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif character in "]}":
            depth -= 1
    return deepest


def _holds_unpaired_surrogate(value: object) -> bool:
    """Tell whether any decoded member name or string holds an unpaired surrogate.

    Parameters
    ----------
    value
        Decoded JSON value.

    Returns
    -------
    bool
        Whether an escape between U+D800 and U+DFFF remained unpaired.
    """
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if any("\ud800" <= character <= "\udfff" for character in item):
                return True
        elif isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def _decode_bounded(
    raw: bytes, source: str, parse_int: Callable[[str], object], *, refuse_unpaired: bool
) -> dict[str, Any]:
    """Decode a strict JSON object nested at most ``MAX_BOUNDED_DEPTH`` deep.

    Parameters
    ----------
    raw
        Complete bytes already read from one source.
    source
        Source label for refusal messages.
    parse_int
        Decoder of each integer token.
    refuse_unpaired
        Whether a string holding an unpaired surrogate escape is refused once
        the whole document has decoded.

    Returns
    -------
    dict[str, Any]
        The decoded top-level object.

    Raises
    ------
    JsonInputRefusalError
        If the bytes are not UTF-8, nest too deeply, are not valid JSON, repeat
        a member name, hold a nonfinite number, an integer ``parse_int``
        refuses or a refused unpaired surrogate, or the top level is not an
        object.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = f"{source}: not UTF-8"
        raise JsonInputRefusalError(message, source) from exc
    if nesting_depth(text) > MAX_BOUNDED_DEPTH:
        message = f"{source}: JSON input exceeds decoder limits"
        raise JsonInputRefusalError(message, source)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
            parse_float=_finite_json_float,
            parse_int=parse_int,
        )
    except json.JSONDecodeError as exc:
        message = f"{source}: invalid JSON"
        raise JsonInputRefusalError(message, source) from exc
    except JsonInputRefusalError as exc:
        message = f"{source}: {exc}"
        raise JsonInputRefusalError(message, source) from exc
    if refuse_unpaired and _holds_unpaired_surrogate(value):
        message = f"{source}: JSON text holds an unpaired surrogate escape"
        raise JsonInputRefusalError(message, source)
    if not isinstance(value, dict):
        message = f"{source}: top-level JSON value must be an object"
        raise JsonInputRefusalError(message, source)
    return value


def parse_bounded_json_object(raw: bytes, source: str) -> dict[str, Any]:
    """Decode a strict JSON object whose limits an independent decoder can share.

    Beyond :func:`parse_json_object`, nesting is at most ``MAX_BOUNDED_DEPTH``
    (checked before decoding), integers fit 64 bits, and no string holds an
    unpaired surrogate escape (checked after decoding). The run analysis uses
    it for every run-bound JSON document, so the native analysis refuses the
    same documents with the same text.

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
    JsonInputRefusalError
        If the bytes are not UTF-8, nest too deeply, are not valid JSON, repeat
        a member name, hold a nonfinite number, an out-of-range integer or an
        unpaired surrogate, or the top level is not an object.
    """
    return _decode_bounded(raw, source, _bounded_json_int, refuse_unpaired=True)


def parse_dispatch_json_object(raw: bytes, source: str) -> dict[str, Any]:
    """Decode a strict JSON object only to choose the analysis that reads it.

    Nesting is bounded as in :func:`parse_bounded_json_object`, before
    decoding, so the choice never depends on the interpreter's recursion
    allowance or integer-conversion limit. Integers stay as their decimal
    text and unpaired surrogate escapes are kept: the chosen analysis applies
    its own bounds to the same bytes.

    Parameters
    ----------
    raw
        Complete bytes already read from one source.
    source
        Source label for refusal messages.

    Returns
    -------
    dict[str, Any]
        The decoded top-level object, with integer tokens as text.

    Raises
    ------
    JsonInputRefusalError
        If the bytes are not UTF-8, nest too deeply, are not valid JSON, repeat
        a member name or hold a nonfinite number, or the top level is not an
        object.
    """
    return _decode_bounded(raw, source, str, refuse_unpaired=False)


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
