# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the measurement-domain manifest validator

"""Contract tests for the manifest validator through its file and command-line surfaces."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest

from conftest import REPOSITORY_ROOT, RunTool
from validate_measurement_domain import DEFAULT_MANIFEST, DEFAULT_SCHEMA, main, validate

if TYPE_CHECKING:
    from pathlib import Path

Mutation = Callable[[dict[str, Any]], None]
CANONICAL_PATH = "03_CODE/SC-NEUROMORPHIC-COMPUTING-SYSTEMS/repositories/LOOP-TIMING-WITNESS"


def committed_manifest() -> dict[str, Any]:
    """Return a deep copy of the committed manifest.

    Returns
    -------
    dict[str, Any]
        Decoded ``measurement-domain.json``.
    """
    return copy.deepcopy(json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")))


def write_json(path: Path, value: object) -> Path:
    """Write one JSON document and return its path.

    Parameters
    ----------
    path
        Destination.
    value
        Document to serialise.

    Returns
    -------
    Path
        ``path``.
    """
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def findings_after(tmp_path: Path, mutate: Mutation) -> list[str]:
    """Validate a mutated copy of the committed manifest.

    Parameters
    ----------
    tmp_path
        Scratch directory.
    mutate
        In-place change applied to the manifest copy.

    Returns
    -------
    list[str]
        Findings of the validator without a registry.
    """
    manifest = committed_manifest()
    mutate(manifest)
    findings, state = validate(
        write_json(tmp_path / "manifest.json", manifest), DEFAULT_SCHEMA, None
    )
    assert state == "not_checked"
    return findings


def contracts(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the design-contract section of a manifest.

    Parameters
    ----------
    manifest
        Decoded manifest.

    Returns
    -------
    dict[str, Any]
        ``design_contracts``.
    """
    section: dict[str, Any] = manifest["design_contracts"]
    return section


def registry_document(**overrides: object) -> dict[str, Any]:
    """Build a registry document shaped like the canonical project registry.

    Parameters
    ----------
    **overrides
        Top-level members to replace.

    Returns
    -------
    dict[str, Any]
        Registry with the portfolio group and one unrelated project.
    """
    document: dict[str, Any] = {
        "groups": [
            {
                "group_id": "SC-NEUROMORPHIC-COMPUTING-SYSTEMS",
                "lifecycle_state": "active",
                "repositories_path": "03_CODE/SC-NEUROMORPHIC-COMPUTING-SYSTEMS/repositories",
            }
        ],
        "projects": [
            {
                "aliases": [{"path": "03_CODE/SC-NEUROCORE"}],
                "canonical_path": (
                    "03_CODE/SC-NEUROMORPHIC-COMPUTING-SYSTEMS/repositories/SC-NEUROCORE"
                ),
                "owning_group_id": "SC-NEUROMORPHIC-COMPUTING-SYSTEMS",
                "project_id": "SC-NEUROCORE",
                "target_kind": "git-repository",
            }
        ],
    }
    document.update(overrides)
    return document


def own_entry(**overrides: object) -> dict[str, Any]:
    """Build a registry entry for this project.

    Parameters
    ----------
    **overrides
        Entry members to replace.

    Returns
    -------
    dict[str, Any]
        Project entry matching the manifest unless overridden.
    """
    entry: dict[str, Any] = {
        "aliases": [],
        "canonical_path": CANONICAL_PATH,
        "owning_group_id": "SC-NEUROMORPHIC-COMPUTING-SYSTEMS",
        "project_id": "LOOP-TIMING-WITNESS",
        "target_kind": "git-repository",
    }
    entry.update(overrides)
    return entry


def test_committed_manifest_is_valid() -> None:
    """The committed manifest passes every layer."""
    assert validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, None) == ([], "not_checked")


def test_command_line_reports_pass_in_a_subprocess(run_tool: RunTool) -> None:
    """The script entry point validates the committed manifest by default."""
    completed = run_tool("validate_measurement_domain")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "measurement-domain: PASS registry=not_checked"


def test_command_line_lists_findings_and_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A defective manifest exits 1 and prints every finding."""
    manifest = committed_manifest()
    manifest["claims"] = ["measured"]
    manifest["capabilities"] = ["witness"]
    path = write_json(tmp_path / "manifest.json", manifest)
    assert main([str(path)]) == 1
    output = capsys.readouterr().out
    assert "measurement-domain: FAIL findings=2" in output
    assert "- capabilities: must be [] at architecture_only" in output
    assert "- claims: must be [] at architecture_only" in output


def test_unreadable_manifest_is_a_finding(tmp_path: Path) -> None:
    """A missing manifest is reported, not raised."""
    findings, state = validate(tmp_path / "absent.json", DEFAULT_SCHEMA, None)
    assert state == "not_checked"
    assert len(findings) == 1
    assert findings[0].startswith("input: ")


def test_repeated_key_in_manifest_is_a_finding(tmp_path: Path) -> None:
    """A manifest that repeats a member name never reaches schema validation."""
    text = DEFAULT_MANIFEST.read_text(encoding="utf-8").replace(
        '"license": "AGPL-3.0-or-later",',
        '"license": "AGPL-3.0-or-later",\n  "license": "MIT",',
    )
    path = tmp_path / "manifest.json"
    path.write_text(text, encoding="utf-8")
    findings, _ = validate(path, DEFAULT_SCHEMA, None)
    assert findings == [f"input: {path}: duplicate JSON key: license"]


def test_invalid_schema_document_is_a_finding(tmp_path: Path) -> None:
    """A schema that is not valid Draft 2020-12 is reported as an input finding."""
    schema = write_json(tmp_path / "schema.json", {"type": "no-such-type"})
    findings, _ = validate(DEFAULT_MANIFEST, schema, None)
    assert len(findings) == 1
    assert "invalid JSON Schema" in findings[0]


def test_structural_errors_stop_before_cross_field_rules(tmp_path: Path) -> None:
    """Schema findings name their document path, root-level ones included."""

    def mutate(manifest: dict[str, Any]) -> None:
        del manifest["purpose"]
        manifest["license"] = "MIT"
        contracts(manifest)["timebase"]["clock_hz"] = "fast"

    findings = findings_after(tmp_path, mutate)
    assert findings == [
        "schema: (root): 'purpose' is a required property",
        "schema: design_contracts/timebase/clock_hz: 'fast' is not of type 'integer'",
        "schema: license: 'AGPL-3.0-or-later' was expected",
    ]


def test_evidence_maturity_beyond_architecture_only_is_refused(tmp_path: Path) -> None:
    """A maturity the schema does not admit is a structural finding."""

    def mutate(manifest: dict[str, Any]) -> None:
        manifest["evidence_maturity"] = "measured"

    assert findings_after(tmp_path, mutate) == [
        "schema: evidence_maturity: 'measured' is not one of ['architecture_only']"
    ]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda m: m.update(project="OTHER-PROJECT"),
            [
                "project: must be 'LOOP-TIMING-WITNESS'",
                (
                    "canonical_path: must be "
                    "'03_CODE/SC-NEUROMORPHIC-COMPUTING-SYSTEMS/repositories/OTHER-PROJECT'"
                ),
            ],
        ),
        (
            lambda m: m.update(
                group="OTHER-GROUP",
                canonical_path="03_CODE/OTHER-GROUP/repositories/LOOP-TIMING-WITNESS",
            ),
            ["group: must be 'SC-NEUROMORPHIC-COMPUTING-SYSTEMS'"],
        ),
        (
            lambda m: m.update(
                canonical_path="03_CODE/SC-NEUROCORE/repositories/LOOP-TIMING-WITNESS"
            ),
            [f"canonical_path: must be {CANONICAL_PATH!r}"],
        ),
        (
            lambda m: m["related_projects"].append(dict(m["related_projects"][0])),
            ["related_projects: project names must be unique"],
        ),
        (
            lambda m: m["related_projects"].append(
                {"project": "LOOP-TIMING-WITNESS", "relation": "itself"}
            ),
            ["related_projects: must not name the project itself"],
        ),
        (
            lambda m: m["target_platform"].update(verified_on_hardware=True),
            ["target_platform.verified_on_hardware: must be false at architecture_only"],
        ),
    ],
)
def test_identity_and_evidence_rules(tmp_path: Path, mutate: Mutation, expected: list[str]) -> None:
    """Identity, relation and evidence violations are each reported exactly."""
    assert findings_after(tmp_path, mutate) == expected


def test_record_field_names_must_be_unique_and_required(tmp_path: Path) -> None:
    """A renamed required field is both a duplicate and a missing field."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_record"]["fields"][4]["name"] = "cycle"

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields: names must be unique",
        "event_record.fields: missing required field 'timebase_ticks'",
    ]


def test_record_without_event_type_field_skips_its_width_rule(tmp_path: Path) -> None:
    """Removing the event-type field reports the gap without a width finding."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_record"]["fields"][0]["name"] = "spare"

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields: missing required field 'event_type'"
    ]


def test_record_fields_must_be_contiguous_and_fill_the_record(tmp_path: Path) -> None:
    """An offset gap and a size mismatch are both reported."""

    def mutate(manifest: dict[str, Any]) -> None:
        record = contracts(manifest)["event_record"]
        record["fields"][3]["offset_bytes"] = 5
        record["record_size_bytes"] = 24

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields.cycle: offset must be 4 (fields are contiguous and ordered)",
        "event_record.fields.timebase_ticks: offset must be 9 (fields are contiguous and ordered)",
        "event_record: fields end at byte 16, record size is 24",
    ]


def test_event_type_width_must_hold_every_event(tmp_path: Path) -> None:
    """More than 256 event names cannot be encoded in a one-byte event type."""

    def mutate(manifest: dict[str, Any]) -> None:
        profile = contracts(manifest)["event_profiles"]["COMPUTE"]
        profile["occasional_events"] = [f"SPARE_{index}" for index in range(250)]

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields.event_type: 261 event types do not fit its width"
    ]


def test_cycle_width_must_hold_the_run_plan(tmp_path: Path) -> None:
    """A repeat longer than the cycle counter range is refused."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["run_plan"]["cycles_per_repeat"] = 2**32 + 1

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields.cycle: 4294967297 cycles per repeat do not fit its width"
    ]


def test_timebase_field_must_be_as_wide_as_the_counter(tmp_path: Path) -> None:
    """A 32-bit timestamp field cannot store a 64-bit counter."""

    def mutate(manifest: dict[str, Any]) -> None:
        record = contracts(manifest)["event_record"]
        record["fields"][4]["type"] = "u32"
        record["record_size_bytes"] = 12

    assert findings_after(tmp_path, mutate) == [
        "event_record.fields.timebase_ticks: narrower than the timebase counter"
    ]


def test_resolution_must_equal_one_clock_period(tmp_path: Path) -> None:
    """A resolution that does not match the clock is refused."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["timebase"]["resolution_ns"] = 5

    assert findings_after(tmp_path, mutate) == [
        "timebase.resolution_ns: must equal one clock period"
    ]


def test_counter_must_not_wrap_within_a_repeat(tmp_path: Path) -> None:
    """A 32-bit counter at 100 MHz wraps in about 43 s, far below one slow repeat."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["timebase"]["counter_bits"] = 32
        record = contracts(manifest)["event_record"]
        record["fields"][4]["type"] = "u32"
        record["record_size_bytes"] = 12

    assert findings_after(tmp_path, mutate) == [
        "timebase.counter_bits: the counter wraps within one repeat at the minimum sample rate"
    ]


def test_control_profile_needs_sample_rate_bounds(tmp_path: Path) -> None:
    """Without CONTROL sample-rate bounds the wrap and buffer rules cannot apply."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_profiles"]["CONTROL"]["sample_rate_hz"] = None
        contracts(manifest)["event_fifo"]["depth_records"] = 1

    assert findings_after(tmp_path, mutate) == [
        "event_profiles.CONTROL.sample_rate_hz: a control loop needs sample-rate bounds"
    ]


def test_event_names_must_be_unique_across_profiles(tmp_path: Path) -> None:
    """A name shared by two profiles would make the event type ambiguous."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_profiles"]["COMPUTE"]["occasional_events"] = ["DEADLINE"]

    assert findings_after(tmp_path, mutate) == [
        "event_profiles: event names must be unique across profiles: ['DEADLINE']"
    ]


def test_interval_rules(tmp_path: Path) -> None:
    """Repeated names, foreign events and zero-length intervals are each reported."""

    def mutate(manifest: dict[str, Any]) -> None:
        intervals = contracts(manifest)["event_profiles"]["CONTROL"]["intervals"]
        intervals.append(
            {"end_event": "SAMPLE_READ", "name": "loop_latency", "start_event": "SAMPLE_READ"}
        )
        intervals.append(
            {"end_event": "OUTPUT_READ", "name": "foreign", "start_event": "INPUT_WRITE"}
        )

    assert findings_after(tmp_path, mutate) == [
        "event_profiles.CONTROL: interval names repeat",
        "event_profiles.CONTROL.intervals.loop_latency: start and end events must differ",
        (
            "event_profiles.CONTROL.intervals.foreign: start_event 'INPUT_WRITE' is not an "
            "event of this profile"
        ),
        (
            "event_profiles.CONTROL.intervals.foreign: end_event 'OUTPUT_READ' is not an "
            "event of this profile"
        ),
    ]


def test_sample_rate_bounds_must_be_ordered(tmp_path: Path) -> None:
    """A default outside its bounds is refused."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_profiles"]["CONTROL"]["sample_rate_hz"]["default"] = 50

    assert findings_after(tmp_path, mutate) == [
        "event_profiles.CONTROL.sample_rate_hz: requires minimum <= default <= maximum"
    ]


def test_buffer_must_outlast_the_slowest_drain(tmp_path: Path) -> None:
    """A buffer of 4000 records fills in exactly 50 ms at 20 kHz and four events, which fails."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_fifo"]["depth_records"] = 4000

    assert findings_after(tmp_path, mutate) == [
        "event_fifo: fills before the slowest drain at the CONTROL maximum sample rate"
    ]


def test_buffer_one_record_above_the_limit_passes(tmp_path: Path) -> None:
    """The comparison is strict and exact: 4001 records outlast a 50 ms drain."""

    def mutate(manifest: dict[str, Any]) -> None:
        contracts(manifest)["event_fifo"]["depth_records"] = 4001

    assert findings_after(tmp_path, mutate) == []


def test_placement_identifiers_must_be_unique(tmp_path: Path) -> None:
    """Two placements with one identifier are refused."""

    def mutate(manifest: dict[str, Any]) -> None:
        placements = contracts(manifest)["controller_placements"]
        placements.append(dict(placements[0]))

    assert findings_after(tmp_path, mutate) == ["controller_placements: identifiers must be unique"]


def test_registry_without_an_entry_reports_pending_registration(tmp_path: Path) -> None:
    """An unregistered project whose path nobody claims is pending registration."""
    registry = write_json(tmp_path / "registry.json", registry_document())
    assert validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, registry) == ([], "pending_registration")


def test_registry_with_a_matching_entry_reports_registered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A matching entry is accepted and the state is printed by the command line."""
    document = registry_document()
    document["projects"].append(own_entry())
    registry = write_json(tmp_path / "registry.json", document)
    assert main(["--registry", str(registry)]) == 0
    assert capsys.readouterr().out.strip() == "measurement-domain: PASS registry=registered"


def test_registry_entry_that_disagrees_is_invalid(tmp_path: Path) -> None:
    """Every disagreeing field of a registered entry is reported."""
    document = registry_document()
    document["projects"].append(
        own_entry(
            canonical_path="03_CODE/LOOP-TIMING-WITNESS",
            owning_group_id="OTHER",
            target_kind="directory",
        )
    )
    registry = write_json(tmp_path / "registry.json", document)
    findings, state = validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, registry)
    assert state == "invalid"
    assert findings == [
        f"registry: canonical_path is '03_CODE/LOOP-TIMING-WITNESS', expected {CANONICAL_PATH!r}",
        "registry: owning_group_id is 'OTHER', expected 'SC-NEUROMORPHIC-COMPUTING-SYSTEMS'",
        "registry: target_kind is 'directory', expected 'git-repository'",
    ]


def test_registry_path_claimed_by_another_project_is_invalid(tmp_path: Path) -> None:
    """A canonical path or retired alias of another project blocks pending registration."""
    document = registry_document()
    document["projects"].append(
        {"aliases": "not-a-list", "canonical_path": CANONICAL_PATH, "project_id": "SQUATTER"}
    )
    document["projects"].append(
        {
            "aliases": ["not-a-mapping", {"path": CANONICAL_PATH}],
            "canonical_path": "x",
            "project_id": "OLD",
        }
    )
    registry = write_json(tmp_path / "registry.json", document)
    findings, state = validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, registry)
    assert state == "invalid"
    assert findings == [
        "registry: canonical path already claimed by 'SQUATTER'",
        "registry: canonical path already claimed by 'OLD'",
    ]


def test_registry_group_must_exist_be_active_and_contain_the_path(tmp_path: Path) -> None:
    """Missing, inactive and mislocated groups are each refused."""
    missing = write_json(tmp_path / "missing.json", registry_document(groups=[]))
    findings, _ = validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, missing)
    assert findings == ["registry: group 'SC-NEUROMORPHIC-COMPUTING-SYSTEMS' is not registered"]
    inactive = registry_document()
    inactive["groups"][0].update(lifecycle_state="retired", repositories_path="03_CODE/ELSEWHERE")
    findings, state = validate(
        DEFAULT_MANIFEST, DEFAULT_SCHEMA, write_json(tmp_path / "inactive.json", inactive)
    )
    assert state == "invalid"
    assert findings == [
        "registry: group 'SC-NEUROMORPHIC-COMPUTING-SYSTEMS' is not active",
        (
            "registry: group repositories path gives '03_CODE/ELSEWHERE/LOOP-TIMING-WITNESS', "
            f"manifest declares {CANONICAL_PATH!r}"
        ),
    ]


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"projects": []}, "registry: groups must be a list of objects"),
        ({"groups": [], "projects": ["x"]}, "registry: projects must be a list of objects"),
    ],
)
def test_malformed_registry_is_invalid(
    tmp_path: Path, document: dict[str, Any], expected: str
) -> None:
    """Registry lists of the wrong shape are refused."""
    findings, state = validate(
        DEFAULT_MANIFEST, DEFAULT_SCHEMA, write_json(tmp_path / "r.json", document)
    )
    assert (findings, state) == ([expected], "invalid")


def test_unreadable_registry_is_invalid(tmp_path: Path) -> None:
    """A registry path that does not exist is a finding, not a pass."""
    findings, state = validate(DEFAULT_MANIFEST, DEFAULT_SCHEMA, tmp_path / "absent.json")
    assert state == "invalid"
    assert len(findings) == 1
    assert findings[0].startswith("registry: ")


def test_defaults_point_at_the_committed_files() -> None:
    """The command-line defaults are the repository's own manifest and schema."""
    assert DEFAULT_MANIFEST == REPOSITORY_ROOT / "measurement-domain.json"
    assert DEFAULT_SCHEMA == REPOSITORY_ROOT / "measurement-domain.schema.json"
