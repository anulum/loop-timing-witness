# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural capture file length and digest binding

"""Read complete bounded run files once and verify their exact bytes before decoding."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from .neural_event_stream import NeuralCaptureRefusalError


def _reference_fields(reference: object, maximum_bytes: int) -> tuple[str, str, int]:
    """Validate the closed path, digest and byte-length reference.

    Parameters
    ----------
    reference
        Original run-manifest file object.
    maximum_bytes
        Caller-admitted size for this source role.

    Returns
    -------
    tuple[str, str, int]
        Original relative name, lowercase SHA-256 and exact declared byte length.

    Raises
    ------
    NeuralCaptureRefusalError
        If fields, types or the declared finite allocation are unsupported. The
        declared length plus its mandatory boundary byte must fit an index-sized
        Python read request.
    """
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256", "byte_length"}:
        message = "Invalid neural capture file reference fields."
        raise NeuralCaptureRefusalError(message)
    name = reference["path"]
    digest = reference["sha256"]
    length = reference["byte_length"]
    if type(name) is not str or not name or "\x00" in name:
        message = "Invalid neural capture file path."
        raise NeuralCaptureRefusalError(message)
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        message = "Invalid neural capture file SHA-256."
        raise NeuralCaptureRefusalError(message)
    if type(length) is not int or not 0 <= length <= min(maximum_bytes, sys.maxsize - 1):
        message = "Invalid neural capture file byte length or allocation."
        raise NeuralCaptureRefusalError(message)
    return name, digest, length


def _read_run_file(directory: Path, name: str, length: int) -> bytes:
    """Read a regular run file within its frozen source directory and finite size.

    Parameters
    ----------
    directory
        Source-custodied immutable run directory.
    name
        Declared relative file name.
    length
        Exact declared byte length, including zero for an empty payload file.

    Returns
    -------
    bytes
        Complete bytes from one read, never a truncated prefix.

    Raises
    ------
    NeuralCaptureRefusalError
        If the name escapes the run directory, the source is not regular or its
        current byte length differs from the declaration.
    OSError
        If the directory or file cannot be resolved or read.
    """
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        message = f"Neural capture path must stay within the run directory: {name}."
        raise NeuralCaptureRefusalError(message)
    root = directory.resolve(strict=True)
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        message = f"Neural capture input is not a regular file within the run directory: {name}."
        raise NeuralCaptureRefusalError(message)
    with path.open("rb") as stream:
        content = stream.read(length + 1)
    if len(content) != length:
        message = f"Neural capture file byte length mismatch: {name}."
        raise NeuralCaptureRefusalError(message)
    return content


def read_neural_bound_file(directory: Path, reference: object, maximum_bytes: int) -> bytes:
    """Read and bind a complete source-custodied file before any neural interpretation.

    Parameters
    ----------
    directory
        Immutable run directory supplied by the complete run loader. Its resolved
        regular files must remain frozen throughout verification and reporting.
    reference
        Closed object containing path, sha256 and byte_length. Relative references
        may resolve only to regular files within this run directory.
    maximum_bytes
        Finite nonnegative allocation admitted by the caller for the source role.
        Zero permits only a present empty file; missing files are never empty data.

    Returns
    -------
    bytes
        Exactly the bytes whose whole length and SHA-256 match the reference.
        Decoders and projection checks must reuse these bytes without re-reading.

    Raises
    ------
    NeuralCaptureRefusalError
        If declarations, placement, readability, size or whole-file digest fail.
    """
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        message = "Invalid neural capture file allocation."
        raise NeuralCaptureRefusalError(message)
    name, digest, length = _reference_fields(reference, maximum_bytes)
    try:
        content = _read_run_file(directory, name, length)
    except OSError as exc:
        message = f"Cannot read neural capture file within the run directory: {name}."
        raise NeuralCaptureRefusalError(message) from exc
    if hashlib.sha256(content).hexdigest() != digest:
        message = f"Neural capture file SHA-256 mismatch: {name}."
        raise NeuralCaptureRefusalError(message)
    return content
