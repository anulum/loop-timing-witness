# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign manifest

"""Load a repeat campaign and the hash-bound run manifests it orders."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator

from .manifest_io import load_json_object, parse_json_object
from .run_manifest import RunInputs, load_run

CAMPAIGN_SCHEMA_PATH: Final = (
    Path(__file__).resolve().parent / "data" / ("repeat-campaign.schema.json")
)
CAMPAIGN_SCHEMA_ID: Final = "loop-timing-witness.repeat-campaign.v1"
_CONFIGURATION_FIELDS: Final = (
    "profile",
    "placement",
    "sample_period_ticks",
    "cycle_count",
    "warmup_cycles",
    "load_case",
    "controller",
    "plant",
    "fault_schedule",
)
_HARDWARE_FILES: Final = ("bitstream", "firmware", "linux_image", "controller_binary")


@dataclass(frozen=True, slots=True)
class CampaignRepeat:
    """One ordered repeat and the outcome of loading its run.

    Attributes
    ----------
    repeat_index
        One-based position in the campaign.
    rebooted_before_run
        Operator declaration that the board rebooted before this repeat.
    run_manifest_sha256
        Verified SHA-256 of the run manifest bytes.
    inputs
        Loaded run, or ``None`` when the run was refused.
    refusal
        Authored refusal message of a refused run, otherwise ``None``.
    """

    repeat_index: int
    rebooted_before_run: bool
    run_manifest_sha256: str
    inputs: RunInputs | None
    refusal: str | None


@dataclass(frozen=True, slots=True)
class CampaignInputs:
    """Validated campaign manifest and its loaded repeats.

    Attributes
    ----------
    manifest
        Campaign manifest validated against the versioned schema.
    manifest_sha256
        SHA-256 of the exact campaign manifest bytes.
    repeats
        Repeats in index order. Every loaded repeat shares one configuration.
    """

    manifest: dict[str, Any]
    manifest_sha256: str
    repeats: tuple[CampaignRepeat, ...]


def run_configuration(inputs: RunInputs) -> dict[str, Any]:
    """Return the run fields that must agree before samples may be pooled.

    Parameters
    ----------
    inputs
        One loaded run.

    Returns
    -------
    dict[str, Any]
        Measurement-domain digest, source tool identity, run configuration,
        instrument floor and hardware artefact digests. Per-run receipts,
        captured inputs and timestamps are deliberately excluded.
    """
    manifest = inputs.manifest
    hardware = manifest["hardware_artifacts"]
    return {
        "measurement_domain_sha256": manifest["measurement_domain"]["sha256"],
        "source_kind": manifest["source"]["kind"],
        "source_tool": manifest["source"]["tool"],
        "source_version": manifest["source"]["version"],
        **{name: manifest[name] for name in _CONFIGURATION_FIELDS},
        "tracking_sampling": manifest.get("tracking_sampling"),
        "instrument_floor_ticks": manifest["instrument"]["floor_ticks"],
        "hardware_artifacts": None
        if hardware is None
        else {
            **{name: hardware[name]["sha256"] for name in _HARDWARE_FILES},
            "libero_version": hardware["libero_version"],
            "toolchain_version": hardware["toolchain_version"],
        },
    }


def _validate_campaign_schema(manifest: dict[str, Any]) -> None:
    """Reject a campaign manifest outside the versioned JSON Schema.

    Parameters
    ----------
    manifest
        Decoded campaign manifest.

    Raises
    ------
    ValueError
        If the first schema error, in path order, is found.
    """
    schema = load_json_object(CAMPAIGN_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "(root)"
        message = f"repeat campaign {location}: {first.message}"
        raise ValueError(message)
    indexes = [item["repeat_index"] for item in manifest["repeats"]]
    if indexes != list(range(1, len(indexes) + 1)):
        message = "repeat_index values must run 1, 2, 3, ... in manifest order"
        raise ValueError(message)


def _run_manifest_path(campaign_directory: Path, relative_path: str) -> Path:
    """Resolve one run manifest without leaving the campaign directory.

    Parameters
    ----------
    campaign_directory
        Resolved directory containing the campaign manifest.
    relative_path
        Schema-valid relative path of a run manifest.

    Returns
    -------
    Path
        Existing regular file inside the campaign directory.

    Raises
    ------
    ValueError
        If the path is absolute, traverses upward, resolves outside the
        directory or is not a regular file.
    """
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        message = f"run manifest path must stay within the campaign directory: {relative_path}"
        raise ValueError(message)
    path = (campaign_directory / relative).resolve()
    if not path.is_relative_to(campaign_directory) or not path.is_file():
        message = f"run manifest is not a regular file inside the campaign: {relative_path}"
        raise ValueError(message)
    return path


def _load_repeat(campaign_directory: Path, item: dict[str, Any]) -> CampaignRepeat:
    """Verify one run manifest digest and load its run.

    Parameters
    ----------
    campaign_directory
        Resolved directory containing the campaign manifest.
    item
        Schema-valid repeat entry.

    Returns
    -------
    CampaignRepeat
        Loaded repeat, or a refused repeat carrying the run's refusal text.

    Raises
    ------
    ValueError
        If the run manifest path or its digest is wrong. The verified bytes
        are the bytes the run loader parses.
    """
    reference = item["run_manifest"]
    path = _run_manifest_path(campaign_directory, reference["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        message = f"run manifest SHA-256 mismatch: {reference['path']}"
        raise ValueError(message)
    try:
        inputs = load_run(path, manifest_bytes=raw)
    except ValueError as error:
        return CampaignRepeat(
            item["repeat_index"], item["rebooted_before_run"], reference["sha256"], None, str(error)
        )
    return CampaignRepeat(
        item["repeat_index"], item["rebooted_before_run"], reference["sha256"], inputs, None
    )


def _check_repeats(repeats: tuple[CampaignRepeat, ...]) -> None:
    """Require distinct runs and one shared configuration across loaded repeats.

    Parameters
    ----------
    repeats
        Repeats in index order.

    Raises
    ------
    ValueError
        If two repeats use the same run ID or a loaded repeat differs from
        the first loaded repeat in any configuration field.
    """
    loaded = [(repeat, repeat.inputs) for repeat in repeats if repeat.inputs is not None]
    run_ids: set[str] = set()
    for repeat, inputs in loaded:
        run_id = inputs.manifest["run_id"]
        if run_id in run_ids:
            message = f"repeat {repeat.repeat_index} reuses run_id {run_id!r}"
            raise ValueError(message)
        run_ids.add(run_id)
    if not loaded:
        return
    first, first_inputs = loaded[0]
    reference = run_configuration(first_inputs)
    for repeat, inputs in loaded[1:]:
        configuration = run_configuration(inputs)
        for name, value in reference.items():
            if configuration[name] != value:
                message = (
                    f"repeat {repeat.repeat_index} differs from repeat "
                    f"{first.repeat_index} in {name}; incompatible runs are not pooled"
                )
                raise ValueError(message)


def load_campaign(manifest_path: Path) -> CampaignInputs:
    """Load a schema-valid repeat campaign and every run it binds.

    A run that its own loader refuses stays in the campaign as a refused
    repeat, so it is reported rather than dropped. Integrity failures of the
    campaign itself refuse the whole campaign.

    Parameters
    ----------
    manifest_path
        Path to one versioned repeat campaign manifest.

    Returns
    -------
    CampaignInputs
        Campaign manifest, its digest and the repeats in index order.

    Raises
    ------
    OSError
        If the campaign or a run manifest cannot be read.
    ValueError
        If JSON, schema, index order, path containment, digest, run identity
        or configuration agreement fails.
    """
    raw = manifest_path.read_bytes()
    manifest = parse_json_object(raw, str(manifest_path))
    _validate_campaign_schema(manifest)
    directory = manifest_path.resolve().parent
    paths = [
        _run_manifest_path(directory, item["run_manifest"]["path"]) for item in manifest["repeats"]
    ]
    if len(set(paths)) != len(paths):
        message = "two repeats bind the same run manifest"
        raise ValueError(message)
    repeats = tuple(_load_repeat(directory, item) for item in manifest["repeats"])
    _check_repeats(repeats)
    return CampaignInputs(manifest, hashlib.sha256(raw).hexdigest(), repeats)
