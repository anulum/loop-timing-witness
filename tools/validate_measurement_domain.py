# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — measurement-domain manifest validator

"""Fail closed when the measurement-domain manifest breaks its contract.

Validation runs in three layers. The manifest must parse as UTF-8 JSON
without repeated member names. Its structure must satisfy the committed JSON
Schema (Draft 2020-12). Its cross-field rules, which a schema cannot express,
must then hold:

- identity: the canonical path is the group's ``repositories/`` child named
  after the project;
- evidence truth: at ``architecture_only`` the capability and claim
  inventories are empty and no hardware verification is declared;
- event record: fields are contiguous from offset zero, fill the declared
  record size exactly, carry the required names, and are wide enough for
  every declared event type and for the planned cycle count;
- timebase: the resolution equals one clock period, and the counter cannot
  wrap during the longest planned run;
- event profiles: event names are unique across profiles, every interval
  joins two distinct events of its own profile, event codes cover each event
  exactly once, and sample-rate bounds are ordered;
- event buffer: at the highest sample rate the buffer takes longer to fill
  than the slowest permitted drain interval.

With ``--registry`` the manifest is also cross-checked against the canonical
project registry: the owning group must exist and be active, and a registered
project entry must agree with the manifest exactly. A project that is not yet
registered is reported as pending registration, provided no other registered
project or retired alias already claims its canonical path.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from manifest_io import load_json_object

PROJECT: Final = "LOOP-TIMING-WITNESS"
GROUP: Final = "SC-NEUROMORPHIC-COMPUTING-SYSTEMS"
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST: Final = REPOSITORY_ROOT / "measurement-domain.json"
DEFAULT_SCHEMA: Final = REPOSITORY_ROOT / "measurement-domain.schema.json"
TYPE_WIDTH_BYTES: Final = {"u8": 1, "u16": 2, "u32": 4, "u64": 8}
REQUIRED_RECORD_FIELDS: Final = ("cycle", "event_type", "timebase_ticks")
NANOSECONDS_PER_SECOND: Final = 1_000_000_000
PERIODIC_PROFILE: Final = "CONTROL"
MIN_GRAY_FIFO_DEPTH: Final = 2
MAX_GRAY_FIFO_DEPTH: Final = 1 << 14


@dataclass(frozen=True, slots=True)
class RegistryResult:
    """Outcome of the registry cross-check.

    Attributes
    ----------
    state
        ``not_checked`` when no registry was given, ``registered`` when a
        matching project entry exists, ``pending_registration`` when the
        project has no entry yet and nothing else claims its path, and
        ``invalid`` when the check produced findings.
    findings
        Human-readable violations; empty unless ``state`` is ``invalid``.
    """

    state: str
    findings: tuple[str, ...] = field(default=())


def schema_findings(manifest: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Validate the manifest structure against the committed JSON Schema.

    Parameters
    ----------
    manifest
        Decoded manifest object.
    schema
        Decoded Draft 2020-12 schema object.

    Returns
    -------
    list[str]
        One finding per schema error, ordered by document path; empty when
        the structure is valid.

    Raises
    ------
    jsonschema.exceptions.SchemaError
        If the schema itself is not a valid Draft 2020-12 schema.
    """
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(manifest),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    findings = []
    for error in errors:
        location = "/".join(str(part) for part in error.absolute_path) or "(root)"
        findings.append(f"schema: {location}: {error.message}")
    return findings


def _identity_findings(manifest: dict[str, Any]) -> list[str]:
    """Check project, group and canonical-path agreement.

    Parameters
    ----------
    manifest
        Structurally valid manifest.

    Returns
    -------
    list[str]
        Identity violations.
    """
    findings = []
    if manifest["project"] != PROJECT:
        findings.append(f"project: must be {PROJECT!r}")
    if manifest["group"] != GROUP:
        findings.append(f"group: must be {GROUP!r}")
    expected_path = f"03_CODE/{manifest['group']}/repositories/{manifest['project']}"
    if manifest["canonical_path"] != expected_path:
        findings.append(f"canonical_path: must be {expected_path!r}")
    related = [entry["project"] for entry in manifest["related_projects"]]
    if len(related) != len(set(related)):
        findings.append("related_projects: project names must be unique")
    if manifest["project"] in related:
        findings.append("related_projects: must not name the project itself")
    return findings


def _evidence_findings(manifest: dict[str, Any]) -> list[str]:
    """Check the evidence-maturity truth rules.

    The schema admits only ``architecture_only``, so these rules apply to
    every structurally valid manifest. A later maturity state needs a schema
    revision together with the evidence rules for that state.

    Parameters
    ----------
    manifest
        Structurally valid manifest.

    Returns
    -------
    list[str]
        Evidence violations.
    """
    findings = []
    if manifest["capabilities"]:
        findings.append("capabilities: must be [] at architecture_only")
    if manifest["claims"]:
        findings.append("claims: must be [] at architecture_only")
    if manifest["target_platform"]["verified_on_hardware"]:
        findings.append("target_platform.verified_on_hardware: must be false at architecture_only")
    return findings


def _all_event_names(profiles: dict[str, Any]) -> list[str]:
    """Return every declared event name in profile order.

    Parameters
    ----------
    profiles
        The ``event_profiles`` object.

    Returns
    -------
    list[str]
        Periodic then occasional events of each profile, duplicates kept.
    """
    names: list[str] = []
    for profile in profiles.values():
        names.extend(profile["periodic_events"])
        names.extend(profile["occasional_events"])
    return names


def _record_findings(contracts: dict[str, Any]) -> list[str]:
    """Check the binary event-record layout.

    Parameters
    ----------
    contracts
        The ``design_contracts`` object.

    Returns
    -------
    list[str]
        Record-layout violations.
    """
    record = contracts["event_record"]
    fields = record["fields"]
    findings = []
    names = [item["name"] for item in fields]
    if len(names) != len(set(names)):
        findings.append("event_record.fields: names must be unique")
    findings.extend(
        f"event_record.fields: missing required field {required!r}"
        for required in REQUIRED_RECORD_FIELDS
        if required not in names
    )
    expected_offset = 0
    for item in fields:
        if item["offset_bytes"] != expected_offset:
            findings.append(
                f"event_record.fields.{item['name']}: offset must be "
                f"{expected_offset} (fields are contiguous and ordered)"
            )
        expected_offset = item["offset_bytes"] + TYPE_WIDTH_BYTES[item["type"]]
    if expected_offset != record["record_size_bytes"]:
        findings.append(
            f"event_record: fields end at byte {expected_offset}, record size is "
            f"{record['record_size_bytes']}"
        )
    widths = {item["name"]: TYPE_WIDTH_BYTES[item["type"]] for item in fields}
    cycles = contracts["run_plan"]["cycles_per_repeat"]
    if "cycle" in widths and cycles > 2 ** (8 * widths["cycle"]):
        findings.append(
            f"event_record.fields.cycle: {cycles} cycles per repeat do not fit its width"
        )
    if "timebase_ticks" in widths and (
        8 * widths["timebase_ticks"] < contracts["timebase"]["counter_bits"]
    ):
        findings.append("event_record.fields.timebase_ticks: narrower than the timebase counter")
    return findings


def _timebase_findings(contracts: dict[str, Any]) -> list[str]:
    """Check clock resolution and counter wrap against the run plan.

    Parameters
    ----------
    contracts
        The ``design_contracts`` object.

    Returns
    -------
    list[str]
        Timebase violations.
    """
    timebase = contracts["timebase"]
    findings = []
    if timebase["resolution_ns"] * timebase["clock_hz"] != NANOSECONDS_PER_SECOND:
        findings.append("timebase.resolution_ns: must equal one clock period")
    control = contracts["event_profiles"][PERIODIC_PROFILE]["sample_rate_hz"]
    if control is not None:
        run_ticks_numerator = contracts["run_plan"]["cycles_per_repeat"] * timebase["clock_hz"]
        if 2 ** timebase["counter_bits"] * control["minimum"] <= run_ticks_numerator:
            findings.append(
                "timebase.counter_bits: the counter wraps within one repeat at "
                "the minimum sample rate"
            )
    return findings


def _profile_findings(contracts: dict[str, Any]) -> list[str]:
    """Check event-profile consistency and sample-rate bounds.

    Parameters
    ----------
    contracts
        The ``design_contracts`` object.

    Returns
    -------
    list[str]
        Profile violations.
    """
    profiles = contracts["event_profiles"]
    findings = []
    all_names = _all_event_names(profiles)
    event_codes = contracts["event_codes"]
    if set(event_codes) != set(all_names):
        findings.append("event_codes: names must match the declared profile events exactly")
    if len(set(event_codes.values())) != len(event_codes):
        findings.append("event_codes: numeric codes must be unique")
    duplicated = sorted({name for name in all_names if all_names.count(name) > 1})
    if duplicated:
        findings.append(f"event_profiles: event names must be unique across profiles: {duplicated}")
    for profile_name, profile in sorted(profiles.items()):
        findings.extend(_interval_findings(profile_name, profile))
        rate = profile["sample_rate_hz"]
        if rate is not None and not (rate["minimum"] <= rate["default"] <= rate["maximum"]):
            findings.append(
                f"event_profiles.{profile_name}.sample_rate_hz: requires "
                "minimum <= default <= maximum"
            )
    if profiles[PERIODIC_PROFILE]["sample_rate_hz"] is None:
        findings.append(
            f"event_profiles.{PERIODIC_PROFILE}.sample_rate_hz: a control loop "
            "needs sample-rate bounds"
        )
    return findings


def _interval_findings(profile_name: str, profile: dict[str, Any]) -> list[str]:
    """Check that every interval of one profile joins two of its own events.

    Parameters
    ----------
    profile_name
        Profile key, used in findings.
    profile
        One ``event_profiles`` entry.

    Returns
    -------
    list[str]
        Interval violations.
    """
    events = set(profile["periodic_events"]) | set(profile["occasional_events"])
    names = [interval["name"] for interval in profile["intervals"]]
    findings = []
    if len(names) != len(set(names)):
        findings.append(f"event_profiles.{profile_name}: interval names repeat")
    for interval in profile["intervals"]:
        label = f"event_profiles.{profile_name}.intervals.{interval['name']}"
        findings.extend(
            f"{label}: {end} {interval[end]!r} is not an event of this profile"
            for end in ("start_event", "end_event")
            if interval[end] not in events
        )
        if interval["start_event"] == interval["end_event"]:
            findings.append(f"{label}: start and end events must differ")
    return findings


def _buffer_findings(contracts: dict[str, Any]) -> list[str]:
    """Check that the event buffer outlasts the slowest drain interval.

    A declared Gray-pointer implementation requires a supported power-of-two
    depth; archived contracts without that declaration retain the sizing rule.
    The buffer fills in ``depth / (maximum_rate * periodic_events)`` seconds
    at the highest sample rate; the drain interval is at most
    ``1 / minimum_drain_rate`` seconds. The comparison uses integers.

    Parameters
    ----------
    contracts
        The ``design_contracts`` object.

    Returns
    -------
    list[str]
        Buffer-sizing violations.
    """
    fifo = contracts["event_fifo"]
    findings = []
    depth = fifo["depth_records"]
    if fifo.get("implementation") == "gray_pointer_dual_clock" and (
        depth < MIN_GRAY_FIFO_DEPTH or depth > MAX_GRAY_FIFO_DEPTH or depth & (depth - 1)
    ):
        findings.append("event_fifo: Gray-pointer depth must be a power of two in [2,16384]")
    for profile_name, profile in sorted(contracts["event_profiles"].items()):
        rate = profile["sample_rate_hz"]
        if rate is None:
            continue
        arrivals = rate["maximum"] * len(profile["periodic_events"])
        if fifo["depth_records"] * fifo["minimum_drain_rate_hz"] <= arrivals:
            findings.append(
                f"event_fifo: fills before the slowest drain at the {profile_name} "
                "maximum sample rate"
            )
    return findings


def _placement_findings(contracts: dict[str, Any]) -> list[str]:
    """Check that controller placement identifiers are unique.

    Parameters
    ----------
    contracts
        The ``design_contracts`` object.

    Returns
    -------
    list[str]
        Placement violations.
    """
    identifiers = [item["identifier"] for item in contracts["controller_placements"]]
    if len(identifiers) != len(set(identifiers)):
        return ["controller_placements: identifiers must be unique"]
    return []


def semantic_findings(manifest: dict[str, Any]) -> list[str]:
    """Apply every cross-field rule to a structurally valid manifest.

    Parameters
    ----------
    manifest
        Manifest that already satisfies the JSON Schema.

    Returns
    -------
    list[str]
        Cross-field violations; empty when the manifest is consistent.
    """
    contracts = manifest["design_contracts"]
    return [
        *_identity_findings(manifest),
        *_evidence_findings(manifest),
        *_record_findings(contracts),
        *_timebase_findings(contracts),
        *_profile_findings(contracts),
        *_buffer_findings(contracts),
        *_placement_findings(contracts),
    ]


def _registry_list(registry: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Return one registry list whose items are all objects.

    Parameters
    ----------
    registry
        Decoded registry object.
    key
        Top-level list name.

    Returns
    -------
    list[dict[str, Any]]
        The list items.

    Raises
    ------
    ValueError
        If the member is missing, not a list, or holds a non-object item.
    """
    value = registry.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        message = f"{key} must be a list of objects"
        raise ValueError(message)
    return value


def registry_cross_check(manifest: dict[str, Any], registry_path: Path) -> RegistryResult:
    """Cross-check the manifest identity against the canonical project registry.

    Parameters
    ----------
    manifest
        Structurally valid manifest.
    registry_path
        Canonical project registry file.

    Returns
    -------
    RegistryResult
        ``registered``, ``pending_registration`` or ``invalid`` with its
        findings.
    """
    try:
        registry = load_json_object(registry_path)
        groups = _registry_list(registry, "groups")
        projects = _registry_list(registry, "projects")
    except (OSError, ValueError) as exc:
        return RegistryResult("invalid", (f"registry: {exc}",))
    findings: list[str] = []
    canonical_path = manifest["canonical_path"]
    group = next((item for item in groups if item.get("group_id") == manifest["group"]), None)
    if group is None:
        findings.append(f"registry: group {manifest['group']!r} is not registered")
    else:
        if group.get("lifecycle_state") != "active":
            findings.append(f"registry: group {manifest['group']!r} is not active")
        expected = f"{group.get('repositories_path')}/{manifest['project']}"
        if expected != canonical_path:
            findings.append(
                f"registry: group repositories path gives {expected!r}, manifest "
                f"declares {canonical_path!r}"
            )
    entry = next(
        (item for item in projects if item.get("project_id") == manifest["project"]),
        None,
    )
    if entry is not None:
        expected_fields = {
            "canonical_path": canonical_path,
            "owning_group_id": manifest["group"],
            "target_kind": "git-repository",
        }
        findings.extend(
            f"registry: {name} is {entry.get(name)!r}, expected {value!r}"
            for name, value in expected_fields.items()
            if entry.get(name) != value
        )
    else:
        for item in projects:
            paths = [item.get("canonical_path")]
            aliases = item.get("aliases")
            if isinstance(aliases, list):
                paths.extend(alias.get("path") for alias in aliases if isinstance(alias, dict))
            if canonical_path in paths:
                findings.append(
                    f"registry: canonical path already claimed by {item.get('project_id')!r}"
                )
    if findings:
        return RegistryResult("invalid", tuple(findings))
    return RegistryResult("registered" if entry is not None else "pending_registration")


def validate(
    manifest_path: Path, schema_path: Path, registry_path: Path | None
) -> tuple[list[str], str]:
    """Run every validation layer for one manifest.

    Parameters
    ----------
    manifest_path
        Manifest file.
    schema_path
        JSON Schema file.
    registry_path
        Optional canonical project registry for the identity cross-check.

    Returns
    -------
    tuple[list[str], str]
        Findings (empty when valid) and the registry state.
    """
    try:
        manifest = load_json_object(manifest_path)
        schema = load_json_object(schema_path)
    except (OSError, ValueError) as exc:
        return [f"input: {exc}"], "not_checked"
    try:
        structural = schema_findings(manifest, schema)
    except SchemaError as exc:
        return [f"input: {schema_path}: invalid JSON Schema: {exc.message}"], "not_checked"
    if structural:
        return structural, "not_checked"
    findings = semantic_findings(manifest)
    if registry_path is None:
        return findings, "not_checked"
    registry = registry_cross_check(manifest, registry_path)
    return [*findings, *registry.findings], registry.state


def main(argv: list[str] | None = None) -> int:
    """Run the manifest validator command-line interface.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when the manifest is valid, ``1`` when any finding exists.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="canonical project registry for the identity cross-check",
    )
    args = parser.parse_args(argv)
    findings, registry_state = validate(args.manifest, args.schema, args.registry)
    if findings:
        print(f"measurement-domain: FAIL findings={len(findings)}")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"measurement-domain: PASS registry={registry_state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
