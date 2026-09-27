# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — run manifest validation

"""Validate one run and bind its input bytes to manifest hashes.

The host never interprets a file before its complete bytes match the digest
declared in the run manifest. Simulation and board runs have distinct schema
requirements; only a board run with every instrument acceptance receipt may
represent a measurement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator, FormatChecker

from manifest_io import load_json_object, parse_json_object
from validate_measurement_domain import schema_findings, semantic_findings

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
DOMAIN_SCHEMA_PATH: Final = REPOSITORY_ROOT / "measurement-domain.schema.json"
RUN_SCHEMA_PATH: Final = REPOSITORY_ROOT / "run-manifest.schema.json"
RUN_SCHEMA_ID: Final = "loop-timing-witness.run-manifest.v1"
WIRE_FIELDS: Final = (
    ("event_type", 0, "u8"),
    ("reserved_byte", 1, "u8"),
    ("reserved_word", 2, "u16"),
    ("cycle", 4, "u32"),
    ("timebase_ticks", 8, "u64"),
)
WIRE_RECORD_BYTES: Final = 16


@dataclass(frozen=True, slots=True)
class RunInputs:
    """Validated run configuration and hash-bound input bytes.

    Attributes
    ----------
    manifest
        Run metadata validated against the versioned run schema.
    domain
        Measurement-domain contract validated against its schema and cross-field rules.
    files
        Complete input bytes keyed by ``events``, ``tracking`` and ``power``;
        optional inputs are absent when the manifest declares ``null``.
    """

    manifest: dict[str, Any]
    domain: dict[str, Any]
    files: dict[str, bytes]


def _load_domain(raw: bytes, source: str) -> dict[str, Any]:
    """Load and validate the run-bound measurement-domain contract.

    Parameters
    ----------
    raw
        Domain bytes already verified against the run manifest.
    source
        Run-relative file name for JSON diagnostics.

    Returns
    -------
    dict[str, Any]
        Valid domain manifest.

    Raises
    ------
    ValueError
        If the domain contract is invalid.
    """
    domain = parse_json_object(raw, source)
    schema = load_json_object(DOMAIN_SCHEMA_PATH)
    findings = schema_findings(domain, schema)
    if not findings:
        findings = semantic_findings(domain)
    if findings:
        message = f"measurement domain invalid: {'; '.join(findings)}"
        raise ValueError(message)
    record = domain["design_contracts"]["event_record"]
    observed_fields = tuple(
        (item["name"], item["offset_bytes"], item["type"]) for item in record["fields"]
    )
    if record["record_size_bytes"] != WIRE_RECORD_BYTES or observed_fields != WIRE_FIELDS:
        message = "measurement domain event record differs from the 16-byte host wire layout"
        raise ValueError(message)
    return domain


def _validate_run_schema(manifest: dict[str, Any]) -> None:
    """Reject a run that does not satisfy the versioned JSON Schema.

    Parameters
    ----------
    manifest
        Decoded run manifest.

    Raises
    ------
    ValueError
        If the run cannot be analysed under this contract.
    """
    schema = load_json_object(RUN_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "(root)"
        message = f"run manifest {location}: {first.message}"
        raise ValueError(message)
    started = datetime.fromisoformat(manifest["started_utc"])
    if started.utcoffset() != UTC.utcoffset(started):
        message = "started_utc must use UTC"
        raise ValueError(message)


def _validate_fault_schedule(manifest: dict[str, Any]) -> None:
    """Check that scheduled faults fit the run and use delay consistently.

    Parameters
    ----------
    manifest
        Structurally valid run manifest.

    Raises
    ------
    ValueError
        If a fault falls outside the run or has an invalid delay.
    """
    for fault in manifest["fault_schedule"]:
        if fault["cycle"] >= manifest["cycle_count"]:
            message = "fault schedule cycle is outside the run"
            raise ValueError(message)
        if fault["kind"] != "delay" and fault["delay_periods"] != 0:
            message = "delay_periods is nonzero for a non-delay fault"
            raise ValueError(message)


def _validate_run_domain(manifest: dict[str, Any], domain: dict[str, Any]) -> None:
    """Reject run fields that disagree with the measurement-domain contract.

    Parameters
    ----------
    manifest
        Structurally valid run manifest.
    domain
        Valid measurement-domain contract.

    Raises
    ------
    ValueError
        If the run uses an undeclared placement, period or fault schedule.
    """
    contracts = domain["design_contracts"]
    if manifest["placement"] not in {
        item["identifier"] for item in contracts["controller_placements"]
    }:
        message = "placement is not declared in measurement-domain.json"
        raise ValueError(message)
    profile = contracts["event_profiles"][manifest["profile"]]
    rate = profile["sample_rate_hz"]
    period = manifest["sample_period_ticks"]
    if rate is not None:
        clock_hz = contracts["timebase"]["clock_hz"]
        if not (rate["minimum"] * period <= clock_hz <= rate["maximum"] * period):
            message = "sample_period_ticks falls outside the declared control rate range"
            raise ValueError(message)
    if manifest["warmup_cycles"] >= manifest["cycle_count"]:
        message = "warmup_cycles must leave at least one analysed cycle"
        raise ValueError(message)
    _validate_fault_schedule(manifest)
    if manifest["source"]["kind"] == "board" and manifest["instrument"]["fifo_overflow_count"]:
        message = "board run with FIFO overflow is invalid measurement evidence"
        raise ValueError(message)


def _read_bound_file(run_directory: Path, item: dict[str, str]) -> bytes:
    """Read one regular file within the run directory and verify its digest.

    Parameters
    ----------
    run_directory
        Resolved directory containing the manifest.
    item
        ``path`` and ``sha256`` from the validated manifest.

    Returns
    -------
    bytes
        The exact bytes used for digest verification and later analysis.

    Raises
    ------
    ValueError
        If the path escapes the directory, is not a regular file or its
        content does not match the declared SHA-256.
    """
    path = _bound_path(run_directory, item)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != item["sha256"]:
        message = f"input SHA-256 mismatch: {item['path']}"
        raise ValueError(message)
    return content


def _bound_path(run_directory: Path, item: dict[str, str]) -> Path:
    """Resolve one manifest path without leaving the run directory.

    Parameters
    ----------
    run_directory
        Resolved directory containing the manifest.
    item
        Validated file reference.

    Returns
    -------
    Path
        Existing regular file inside the run directory.

    Raises
    ------
    ValueError
        If the file reference escapes or is not a regular file.
    """
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        message = f"input path must stay within the run directory: {item['path']}"
        raise ValueError(message)
    path = (run_directory / relative).resolve()
    if not path.is_relative_to(run_directory) or not path.is_file():
        message = f"input is not a regular file inside the run directory: {item['path']}"
        raise ValueError(message)
    return path


def _verify_artifact(run_directory: Path, item: dict[str, str]) -> None:
    """Stream-check one referenced source or hardware artefact.

    Parameters
    ----------
    run_directory
        Resolved directory containing the manifest.
    item
        Validated path and SHA-256.

    Raises
    ------
    ValueError
        If the complete file does not match the declared SHA-256.
    """
    digest = hashlib.sha256()
    with _bound_path(run_directory, item).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != item["sha256"]:
        message = f"artefact SHA-256 mismatch: {item['path']}"
        raise ValueError(message)


def load_run(manifest_path: Path) -> RunInputs:
    """Load a schema-valid run and verify every referenced input file.

    Parameters
    ----------
    manifest_path
        Path to one versioned run manifest.

    Returns
    -------
    RunInputs
        Domain, run metadata and hash-bound input bytes.

    Raises
    ------
    OSError
        If the manifest, domain or input bytes cannot be read.
    ValueError
        If JSON, schema, semantic or digest validation fails.
    """
    manifest = load_json_object(manifest_path)
    _validate_run_schema(manifest)
    directory = manifest_path.resolve().parent
    domain_item = manifest["measurement_domain"]
    domain = _load_domain(_read_bound_file(directory, domain_item), domain_item["path"])
    _validate_run_domain(manifest, domain)
    for item in manifest["source"]["files"]:
        _verify_artifact(directory, item)
    if manifest["hardware_artifacts"] is not None:
        for name in ("bitstream", "firmware", "linux_image", "controller_binary"):
            _verify_artifact(directory, manifest["hardware_artifacts"][name])
    files: dict[str, bytes] = {}
    for name in ("native_metadata", "host_load"):
        if name in manifest:
            files[name] = _read_bound_file(directory, manifest[name])
    for name, item in manifest["files"].items():
        if item is not None:
            files[name] = _read_bound_file(directory, item)
    return RunInputs(manifest, domain, files)
