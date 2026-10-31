# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — descriptor-bound public neural file acquisition

"""Read finite regular acquisition files through no-follow directory descriptors."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from contextlib import ExitStack
from typing import TYPE_CHECKING

from .neural_event_stream import NeuralCaptureRefusalError

_PATH_LIMIT = 4096
_MANIFEST_LIMIT = 65536

if TYPE_CHECKING:
    from pathlib import Path


def _read(directory: Path, name: str, limit: int, *, portable: bool = True) -> bytes:
    """Open every relative component without following symlinks or blocking on FIFO.

    Parameters
    ----------
    directory
        Selected immutable acquisition root.
    name
        Canonical portable within-root name.
    limit
        Maximum complete bytes, with one extra byte for boundary detection.
    portable
        Require canonical referenced-file paths; the caller-selected root name
        may use the host filesystem naming rules.

    Returns
    -------
    bytes
        Complete file data within the finite allocation.

    Raises
    ------
    NeuralCaptureRefusalError
        If placement, file kind, readability or allocation cannot be established.
    """
    if portable and (
        not name
        or len(name) > _PATH_LIMIT
        or any(
            part in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None
            for part in name.split("/")
        )
    ):
        message = f"Invalid within-run original path: {name}."
        raise NeuralCaptureRefusalError(message)
    # Each failure names the step it interrupted, as the native reader does.
    stage = "Run directory descriptor unavailable."
    try:
        with ExitStack() as stack:
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
            descriptor = os.open(directory, flags | os.O_DIRECTORY)
            stack.callback(os.close, descriptor)
            stage = f"Cannot open original parent without symlinks: {name}."
            for part in name.split("/")[:-1]:
                descriptor = os.open(part, flags | os.O_DIRECTORY, dir_fd=descriptor)
                stack.callback(os.close, descriptor)
            stage = f"Cannot open original file without symlinks: {name}."
            target = os.open(
                name.rsplit("/", maxsplit=1)[-1], flags | os.O_NONBLOCK, dir_fd=descriptor
            )
            with os.fdopen(target, "rb") as stream:
                stage = f"Cannot inspect original file descriptor: {name}."
                mode = os.fstat(stream.fileno()).st_mode
                if not stat.S_ISREG(mode):
                    message = f"Original file is not regular within the run: {name}."
                    raise NeuralCaptureRefusalError(message)
                stage = f"Cannot read full original file: {name}."
                raw = stream.read(limit + 1)
    except OSError as exc:
        raise NeuralCaptureRefusalError(stage) from exc
    if len(raw) > limit:
        message = f"Original file exceeds allocation: {name}."
        raise NeuralCaptureRefusalError(message)
    return raw


def read_neural_run_file(
    directory: Path,
    reference: object,
    maximum_bytes: int,
    *,
    expected_bytes: bytes | None = None,
    mismatch_message: str = "Public neural file differs from its expected complete bytes.",
) -> bytes:
    """Bind one complete public acquisition file before interpreting its bytes.

    Parameters
    ----------
    directory
        Immutable acquisition root, already resolved by the complete run loader.
    reference
        Closed path, lowercase SHA-256 and exact nonnegative byte-length object.
    maximum_bytes
        Finite caller-owned allocation for the file's semantic role.
    expected_bytes
        Optional consumer-owned original body. Compare complete bytes before
        hashing, independently of the acquisition's declared digest.
    mismatch_message
        Caller-owned diagnostic for a differing expected body.

    Returns
    -------
    bytes
        Complete original bytes with exact length and whole-file digest equality.

    Raises
    ------
    NeuralCaptureRefusalError
        If fields, types, allocation, file placement or complete identity fail.
    """
    if (
        type(maximum_bytes) is not int
        or not 0 <= maximum_bytes <= 8 * 1024 * 1024
        or not isinstance(reference, dict)
        or set(reference) != {"path", "sha256", "byte_length"}
        or type(reference["path"]) is not str
        or type(reference["sha256"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is None
        or type(reference["byte_length"]) is not int
        or not 0 <= reference["byte_length"] <= maximum_bytes
    ):
        name = reference.get("path") if isinstance(reference, dict) else None
        message = (
            f"Invalid original file reference: {name}."
            if type(name) is str
            else "Invalid original file reference."
        )
        raise NeuralCaptureRefusalError(message)
    raw = _read(directory, reference["path"], reference["byte_length"])
    if expected_bytes is not None and raw != expected_bytes:
        raise NeuralCaptureRefusalError(mismatch_message)
    if (
        len(raw) != reference["byte_length"]
        or hashlib.sha256(raw).hexdigest() != reference["sha256"]
    ):
        message = f"Original whole length/SHA-256 differs: {reference['path']}."
        raise NeuralCaptureRefusalError(message)
    return raw


def read_neural_manifest_root(path: Path) -> bytes:
    """Acquire one complete root manifest without a second unbounded path read.

    Parameters
    ----------
    path
        Caller-selected original root manifest.

    Returns
    -------
    bytes
        One complete regular manifest, bounded to 65,536 bytes.

    Raises
    ------
    NeuralCaptureRefusalError
        If the original cannot be acquired through a no-follow finite descriptor.
    """
    # Each failure names the step it interrupted, as the native reader does.
    stage = "Cannot read neural manifest as a regular file without symlinks."
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            stage = "Cannot inspect neural manifest descriptor."
            regular = stat.S_ISREG(os.fstat(stream.fileno()).st_mode)
            stage = "Cannot read neural manifest bytes."
            raw = stream.read(_MANIFEST_LIMIT + 1) if regular else b""
    except (OSError, ValueError) as exc:
        raise NeuralCaptureRefusalError(stage) from exc
    if not regular:
        message = "Neural manifest must be a regular file."
        raise NeuralCaptureRefusalError(message)
    if len(raw) > _MANIFEST_LIMIT:
        message = "Neural manifest exceeds its byte allocation."
        raise NeuralCaptureRefusalError(message)
    return raw


def read_run_dispatch_bytes(path: Path) -> bytes:
    """Acquire a finite root snapshot before choosing legacy or neural analysis.

    Parameters
    ----------
    path
        Caller-selected manifest for the existing analysis command.

    Returns
    -------
    bytes
        Complete root bytes, at most 16 MiB. The neural decoder separately
        enforces its narrower 65,536-byte carrier limit.

    Raises
    ------
    NeuralCaptureRefusalError
        If descriptor, placement or finite command-dispatch allocation fails.
    """
    try:
        return _read(path.parent.resolve(strict=True), path.name, 16 * 1048576, portable=False)
    except (OSError, ValueError) as exc:
        message = "Cannot acquire a finite regular run manifest for analysis."
        raise NeuralCaptureRefusalError(message) from exc
