# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — closed public neural manifest declarations

"""Validate neural manifest declarations independently of trusted source admission."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from importlib.resources import files
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from jsonschema import Draft202012Validator

from .manifest_io import JsonInputRefusalError, parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError

if TYPE_CHECKING:
    from pathlib import Path

NEURAL_SCHEMA_ID: Final = "loop-timing-witness.neural-step-run.v1"
NEURAL_SCHEMA_SHA256: Final = "846d131e51cff0dee88d8c9484e435eb02444e0f0a18b58e9d5f053633164f8f"
NEURAL_MANIFEST_LIMIT: Final = 65536
NEURAL_SOURCE_BYTES_LIMIT: Final = 1048576
NEURAL_PATH_LENGTH_LIMIT: Final = 4096
_ROOT_REFERENCES: Final = (
    "tool_receipt",
    "input_trace",
    "numerical_trace",
    "numerical_projection",
    "reference_projection",
    "service_trace",
    "clock_schedule_ref",
    "source_contract_ref",
)


def _manifest_bytes(path: Path) -> bytes:
    """Read one bounded regular manifest without following its final symlink.

    Parameters
    ----------
    path
        Caller-selected manifest; referenced run files are not opened here.

    Returns
    -------
    bytes
        Complete root bytes, at most the fixed manifest allocation.

    Raises
    ------
    NeuralCaptureRefusalError
        If the manifest is absent, unreadable, nonregular, a symlink or oversized.
    """
    if "\x00" in os.fspath(path):
        message = "Neural manifest path contains an invalid NUL character."
        raise NeuralCaptureRefusalError(message)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                message = "Neural manifest must be a regular file."
                raise NeuralCaptureRefusalError(message)
            raw = stream.read(NEURAL_MANIFEST_LIMIT + 1)
    except OSError as exc:
        message = "Cannot read neural manifest as a regular file without symlinks."
        raise NeuralCaptureRefusalError(message) from exc
    if len(raw) > NEURAL_MANIFEST_LIMIT:
        message = "Neural manifest exceeds its byte allocation."
        raise NeuralCaptureRefusalError(message)
    return raw


def _has_decimal(value: object) -> bool:
    """Find decimal encodings in the integer-only manifest tree.

    Parameters
    ----------
    value
        Strictly decoded JSON value.

    Returns
    -------
    bool
        Whether any number uses a decimal representation, including integral floats.
    """
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_has_decimal(child) for child in value.values())
    if isinstance(value, list):
        return any(_has_decimal(child) for child in value)
    return False


def _reference_path(reference: dict[str, Any], limit: int) -> str:
    """Require a portable canonical relative path and the role's byte allocation.

    Parameters
    ----------
    reference
        Structurally validated closed file reference.
    limit
        Maximum complete bytes admitted for this reference role.

    Returns
    -------
    str
        Original within-run relative name.

    Raises
    ------
    NeuralCaptureRefusalError
        If the path escapes, aliases components or exceeds a finite bound.
    """
    name: str = reference["path"]
    relative = PurePosixPath(name)
    if re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is None:
        message = "Neural file reference requires an exact lowercase SHA-256."
        raise NeuralCaptureRefusalError(message)
    if (
        not relative.parts
        or len(name) > NEURAL_PATH_LENGTH_LIMIT
        or relative.is_absolute()
        or relative.as_posix() != name
        or any(re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None for part in relative.parts)
        or ".." in relative.parts
        or reference["byte_length"] > limit
    ):
        message = "Neural file reference requires a bounded portable within-run path."
        raise NeuralCaptureRefusalError(message)
    return name


def _require_exact_identity(manifest: dict[str, Any]) -> None:
    """Require complete run-ID and source-pin tokens after structural validation.

    Parameters
    ----------
    manifest
        Schema-valid carrier whose pattern fields still need whole-string checks.

    Raises
    ------
    NeuralCaptureRefusalError
        If a token has trailing data accepted by an end-of-line schema anchor.
    """
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", manifest["run_id"]) is None or any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for digest in manifest["sc_body_pins"].values()
    ):
        message = "Neural run identity and source pins require exact grammar."
        raise NeuralCaptureRefusalError(message)


def load_neural_manifest(path: Path) -> dict[str, Any]:
    """Read and validate the closed public carrier without admitting its sources.

    Parameters
    ----------
    path
        Public neural manifest. Source, trace, runtime and receipt files remain
        unopened; their declarations require the separate complete run verifier.

    Returns
    -------
    dict[str, Any]
        Validated declarations only. This is neither a bound run nor a verdict
        on numerical equality, runtime selection, capture or source adoption.

    Raises
    ------
    NeuralCaptureRefusalError
        If root bytes, the installed schema, closed shape, exact integers,
        reference paths or finite manifest/source allocations are unsupported.
    """
    return decode_neural_manifest(_manifest_bytes(path))


def decode_neural_manifest(raw: bytes) -> dict[str, Any]:
    """Validate one already acquired bounded public carrier byte string.

    Parameters
    ----------
    raw
        Original manifest bytes, retained by the complete acquisition loader.

    Returns
    -------
    dict[str, Any]
        Closed declarations only; source and runtime admission remain separate.

    Raises
    ------
    NeuralCaptureRefusalError
        If bytes, schema, exact integer encodings or reference laws fail.
    """
    if len(raw) > NEURAL_MANIFEST_LIMIT:
        message = "Neural manifest exceeds its byte allocation."
        raise NeuralCaptureRefusalError(message)
    schema_raw = _installed_schema_bytes()
    try:
        manifest = parse_json_object(raw, "neural manifest")
        schema = parse_json_object(schema_raw, "installed neural schema")
    except JsonInputRefusalError as exc:
        message = "Neural manifest must contain a strict UTF-8 JSON object."
        raise NeuralCaptureRefusalError(message) from exc
    if not Draft202012Validator(schema).is_valid(manifest) or _has_decimal(manifest):
        message = "Neural manifest violates its closed schema or exact integer contract."
        raise NeuralCaptureRefusalError(message)
    _require_exact_identity(manifest)
    references = manifest["source_files"]
    paths = [_reference_path(ref, NEURAL_SOURCE_BYTES_LIMIT) for ref in references]
    if len(set(paths)) != len(paths):
        message = "Neural source references contain a duplicate path."
        raise NeuralCaptureRefusalError(message)
    for name in _ROOT_REFERENCES:
        _reference_path(manifest[name], NEURAL_MANIFEST_LIMIT)
    for channel in manifest["channels"]:
        for name in ("capture", "payload", "markers"):
            _reference_path(channel[name], NEURAL_MANIFEST_LIMIT)
    return manifest


def _installed_schema_bytes() -> bytes:
    """Read the exact consumer-owned public carrier schema.

    Returns
    -------
    bytes
        Original packaged schema bytes with the approved digest.

    Raises
    ------
    NeuralCaptureRefusalError
        If installation bytes are absent or differ from the approved schema.
    """
    try:
        schema_raw = (
            files("loop_timing_witness").joinpath("data/neural-step-run.schema.json").read_bytes()
        )
    except OSError as exc:
        message = "Installed neural manifest schema is unavailable."
        raise NeuralCaptureRefusalError(message) from exc
    if hashlib.sha256(schema_raw).hexdigest() != NEURAL_SCHEMA_SHA256:
        message = "Installed neural manifest schema differs from its admitted body."
        raise NeuralCaptureRefusalError(message)
    return schema_raw
