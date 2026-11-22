# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — input reading, file digests and atomic output

"""Input reading, file digests and atomic artefact writing for the repository tools.

Inputs are opened non-blocking and judged on the opened descriptor. A JSON input is read whole
and decoded by :mod:`loop_timing_witness.strict_json`, labelled with its path. Writes replace
the destination atomically, so an interrupted write never leaves a truncated artefact behind.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from loop_timing_witness.strict_json import parse_bounded_json_object, parse_json_object


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
    return parse_json_object(read_input_bytes(path), str(path))


def load_bounded_json_object(path: Path) -> dict[str, Any]:
    """Read a strict JSON object from a filesystem path under the bounded rules.

    The bytes are decoded by :func:`parse_bounded_json_object`, labelled with
    the path as given, so an independent decoder refuses the same documents
    with the same text.

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
        If the bytes violate the bounded strict JSON contract.
    """
    return parse_bounded_json_object(read_input_bytes(path), str(path))


def open_input(path: Path) -> BinaryIO:
    """Open one input file for reading, failing as ``open(path, "rb")`` does, without blocking.

    The file is opened non-blocking and the opened descriptor, not the name, is judged, so a
    FIFO cannot stall the reader and the file read is the file checked. A directory is refused
    as ``open`` refuses it; a FIFO is refused with ``EINVAL`` naming the path. A device such as
    ``/dev/null`` reads as before, and a socket cannot be opened at all (``ENXIO``). The native
    analysis opens and refuses alike.

    Parameters
    ----------
    path
        File to open.

    Returns
    -------
    BinaryIO
        Open binary stream positioned at the start.

    Raises
    ------
    OSError
        If the file cannot be opened or inspected, or is a directory or a FIFO.
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        # Judged before a stream wraps the descriptor, which would refuse a directory
        # naming the descriptor number instead of the path.
        _refuse_kind(os.fstat(descriptor).st_mode, path)
    except BaseException:
        os.close(descriptor)
        raise
    return os.fdopen(descriptor, "rb")


def _refuse_kind(mode: int, path: Path) -> None:
    """Refuse a directory as ``open`` does, and a FIFO, which could block the reader.

    Parameters
    ----------
    mode
        File mode of the opened descriptor.
    path
        Name the refusal states.

    Raises
    ------
    OSError
        ``EISDIR`` for a directory, ``EINVAL`` for a FIFO.
    """
    if stat.S_ISDIR(mode):
        raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), str(path))
    if stat.S_ISFIFO(mode):
        raise OSError(errno.EINVAL, os.strerror(errno.EINVAL), str(path))


def read_input_bytes(path: Path) -> bytes:
    """Read one whole input file as :func:`open_input` admits it.

    Parameters
    ----------
    path
        File to read.

    Returns
    -------
    bytes
        Complete file content.

    Raises
    ------
    OSError
        If the file cannot be opened, inspected or read, or is a directory or a FIFO.
    """
    with open_input(path) as stream:
        return stream.read()


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
    return hashlib.sha256(read_input_bytes(path)).hexdigest()


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
