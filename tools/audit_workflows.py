# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — workflow ownership, privilege and pinning guard

"""Fail closed when the workflow definitions drift from their inventory or policy.

Workflow YAML is executable governance code. This guard proves the workflow
tree against the versioned inventory ``.github/workflow-inventory.json``:

- the inventory is well-formed JSON without repeated keys, and every workflow
  file on disk is declared exactly once with one owner and one category of
  the eleven-category responsibility taxonomy; declared and omitted
  categories partition the taxonomy;
- workflow YAML parses without repeated mapping keys and stays inside the
  inventory's line and byte ceilings;
- top-level permissions are empty, every job declares its own permissions,
  and publication privileges belong only to explicitly authorised jobs;
- privileged triggers (``pull_request_target``, ``workflow_run``) are absent,
  reusable workflows expose only ``workflow_call``, and every other workflow
  declares a concurrency group;
- every job that runs steps has a bounded timeout; dependencies belong to the
  coordinator or the exact validated-build/publication pairs;
- every external action is pinned to a 40-hexadecimal commit, container
  images are pinned by digest, local reusable calls resolve to declared
  reusable workflows, and every checkout disables credential persistence;
- unrelated write-authority workflows are absent; authorised project publishers
  have exact source, prerequisite, environment and permissions boundaries;
- the coordinator carries only trigger policy, reusable calls and one
  aggregate gate that runs always, needs every call exactly once, and fails
  on any non-success result.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Final

import yaml
from workflow_publication import PUBLICATION_JOBS, publication_findings

from manifest_io import load_json_object

INVENTORY_RELATIVE: Final = Path(".github/workflow-inventory.json")
WORKFLOWS_RELATIVE: Final = Path(".github/workflows")
INVENTORY_SCHEMA: Final = "loop-timing-witness.workflow-inventory.v1"
INVENTORY_SCHEMA_VERSION: Final = "1.0.0"
TAXONOMY: Final = frozenset(range(1, 12))
KINDS: Final = frozenset({"coordinator", "reusable", "standalone"})
ENTRY_KEYS: Final = frozenset({"category", "file", "jobs", "kind", "owner"})
WORKFLOW_FILE: Final = re.compile(r"^[a-z0-9][a-z0-9-]*\.ya?ml$")
PINNED_ACTION: Final = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
PINNED_IMAGE: Final = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")
LOCAL_REUSABLE_PREFIX: Final = "./.github/workflows/"
PRIVILEGED_TRIGGERS: Final = frozenset({"pull_request_target", "workflow_run"})
WRITE_AUTHORITY_WORKFLOWS: Final = frozenset(
    {
        "deploy.yml",
        "docker-publish.yml",
        "metrics.yml",
        "pages.yml",
        "release.yml",
        "stale.yml",
    }
)
ALLOWED_WRITE_SCOPES: Final = frozenset({"security-events"})
COORDINATOR_KEYS: Final = frozenset({"name", "on", "permissions", "concurrency", "jobs"})
MAXIMUM_TIMEOUT_MINUTES: Final = 360


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects repeated keys inside one mapping."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    """Construct one mapping and refuse a key that appears twice.

    Parameters
    ----------
    loader
        Active loader.
    node
        Mapping node being constructed.

    Returns
    -------
    dict[Any, Any]
        The constructed mapping.

    Raises
    ------
    yaml.constructor.ConstructorError
        If a key repeats.
    """
    keys: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in keys:
            context = "while constructing a mapping"
            problem = f"found duplicate key {key!r}"
            raise yaml.constructor.ConstructorError(
                context, node.start_mark, problem, key_node.start_mark
            )
        keys.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_workflow(text: str) -> dict[str, Any]:
    """Parse one workflow document with duplicate-key rejection.

    YAML 1.1 reads the bare key ``on`` as the boolean ``True``; the parsed
    mapping is normalised so the trigger block is always under ``"on"``.

    Parameters
    ----------
    text
        Workflow YAML.

    Returns
    -------
    dict[str, Any]
        Parsed workflow with string keys.

    Raises
    ------
    ValueError
        If the text is not valid YAML, repeats a key, or is not a mapping.
    """
    loader = _UniqueKeyLoader(text)
    try:
        parsed = loader.get_single_data()
    except yaml.YAMLError as exc:
        message = f"YAML parse failure: {exc}"
        raise ValueError(message) from exc
    finally:
        loader.dispose()
    if not isinstance(parsed, dict):
        message = "workflow must be a YAML mapping"
        raise ValueError(message)
    return {("on" if key is True else str(key)): value for key, value in parsed.items()}


def _entry_is_valid(entry: object) -> bool:
    """Tell whether one inventory entry has the required exact shape.

    Parameters
    ----------
    entry
        Decoded ``workflows`` item.

    Returns
    -------
    bool
        ``True`` for an object with exactly the entry keys, a plain workflow
        file name, a known kind, a taxonomy category, a non-empty list of job
        names and a non-blank owner.
    """
    return (
        isinstance(entry, dict)
        and set(entry) == ENTRY_KEYS
        and isinstance(entry["file"], str)
        and WORKFLOW_FILE.match(entry["file"]) is not None
        and isinstance(entry["kind"], str)
        and entry["kind"] in KINDS
        and type(entry["category"]) is int
        and entry["category"] in TAXONOMY
        and isinstance(entry["jobs"], list)
        and bool(entry["jobs"])
        and all(isinstance(job, str) for job in entry["jobs"])
        and isinstance(entry["owner"], str)
        and bool(entry["owner"].strip())
    )


def inventory_findings(inventory: dict[str, Any]) -> list[str]:
    """Validate the inventory document shape before it governs the tree.

    Parameters
    ----------
    inventory
        Decoded inventory object.

    Returns
    -------
    list[str]
        Shape violations; the tree is audited only when this is empty.
    """
    findings = []
    if inventory.get("schema") != INVENTORY_SCHEMA:
        findings.append(f"inventory: schema must be {INVENTORY_SCHEMA!r}")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        findings.append(f"inventory: schema_version must be {INVENTORY_SCHEMA_VERSION!r}")
    if not isinstance(inventory.get("coordinator"), str):
        findings.append("inventory: coordinator must name a workflow file")
    limits = inventory.get("size_limits")
    if not (
        isinstance(limits, dict)
        and set(limits) == {"max_bytes", "max_lines"}
        and all(type(value) is int and value > 0 for value in limits.values())
    ):
        findings.append("inventory: size_limits needs positive integer max_bytes and max_lines")
    omitted = inventory.get("omitted_categories")
    if not (isinstance(omitted, list) and all(type(item) is int for item in omitted)):
        findings.append("inventory: omitted_categories must be a list of integers")
    gate = inventory.get("aggregate_gate")
    if not (
        isinstance(gate, dict)
        and isinstance(gate.get("workflow"), str)
        and isinstance(gate.get("job"), str)
    ):
        findings.append("inventory: aggregate_gate needs workflow and job names")
    entries = inventory.get("workflows")
    if not isinstance(entries, list) or not entries:
        findings.append("inventory: workflows must be a non-empty list")
        return findings
    findings.extend(
        f"inventory: workflows[{index}] needs exactly file, kind, category 1-11, "
        "non-empty jobs and owner"
        for index, entry in enumerate(entries)
        if not _entry_is_valid(entry)
    )
    return findings


def _reference_finding(label: str, reference: str, reusables: set[str]) -> str | None:
    """Check one ``uses`` reference for pinning or local resolution.

    Parameters
    ----------
    label
        ``file: job`` prefix for the finding.
    reference
        The ``uses`` value.
    reusables
        Declared reusable workflow file names.

    Returns
    -------
    str or None
        A finding, or ``None`` when the reference is acceptable.
    """
    if reference.startswith(LOCAL_REUSABLE_PREFIX):
        if reference.removeprefix(LOCAL_REUSABLE_PREFIX) in reusables:
            return None
        return f"{label}: {reference!r} is not a declared reusable workflow"
    if reference.startswith("docker://"):
        if PINNED_IMAGE.match(reference) is not None:
            return None
        return f"{label}: image {reference!r} is not pinned by digest"
    if PINNED_ACTION.match(reference) is not None:
        return None
    return f"{label}: action {reference!r} is not pinned to a commit"


def _step_findings(label: str, steps: list[Any], reusables: set[str]) -> list[str]:
    """Check the step-level action references and checkout credentials.

    Parameters
    ----------
    label
        ``file: job`` prefix for findings.
    steps
        Parsed ``steps`` list.
    reusables
        Declared reusable workflow file names.

    Returns
    -------
    list[str]
        Step violations.
    """
    findings = []
    for step in steps:
        reference = step.get("uses") if isinstance(step, dict) else None
        if not isinstance(reference, str):
            continue
        finding = _reference_finding(label, reference, reusables)
        if finding is not None:
            findings.append(finding)
        options = step.get("with")
        persist = options.get("persist-credentials") if isinstance(options, dict) else None
        if reference.startswith("actions/checkout@") and persist is not False:
            findings.append(f"{label}: checkout must set persist-credentials: false")
    return findings


def _job_findings(file: str, kind: str, name: str, job: object, reusables: set[str]) -> list[str]:
    """Check one job for privilege, timeout, dependency and pinning rules.

    Parameters
    ----------
    file
        Workflow file name.
    kind
        Inventory kind of the workflow.
    name
        Job identifier.
    job
        Parsed job value.
    reusables
        Declared reusable workflow file names.

    Returns
    -------
    list[str]
        Job violations.
    """
    label = f"{file}: job {name}"
    if not isinstance(job, dict):
        return [f"{label}: must be a mapping"]
    findings: list[str] = []
    permissions = job.get("permissions")
    if isinstance(permissions, dict):
        allowed = ALLOWED_WRITE_SCOPES | PUBLICATION_JOBS.get((file, name), frozenset())
        findings.extend(
            f"{label}: write scope {scope!r} is not permitted"
            for scope, level in permissions.items()
            if level == "write" and scope not in allowed
        )
    else:
        findings.append(f"{label}: must declare a permissions mapping")
    if (
        kind != "coordinator"
        and (file, name)
        not in {
            ("docs.yml", "deploy"),
            ("publish.yml", "publish"),
            ("reusable-tests.yml", "coverage"),
            ("pypi-downloads.yml", "snapshot"),
        }
        and "needs" in job
    ):
        findings.append(f"{label}: only the coordinator may declare needs")
    if isinstance(job.get("uses"), str):
        finding = _reference_finding(label, job["uses"], reusables)
        if finding is not None:
            findings.append(finding)
    steps = job.get("steps")
    if steps is not None:
        timeout = job.get("timeout-minutes")
        if not (type(timeout) is int and 0 < timeout <= MAXIMUM_TIMEOUT_MINUTES):
            findings.append(
                f"{label}: timeout-minutes must be an integer in 1..{MAXIMUM_TIMEOUT_MINUTES}"
            )
        findings.extend(_step_findings(label, steps if isinstance(steps, list) else [], reusables))
    return findings


def _trigger_findings(entry: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    """Check triggers and concurrency for the workflow's kind.

    Parameters
    ----------
    entry
        Inventory entry.
    workflow
        Parsed workflow document.

    Returns
    -------
    list[str]
        Trigger violations.
    """
    file = entry["file"]
    triggers = workflow.get("on")
    names = set(triggers) if isinstance(triggers, dict) else {str(triggers)}
    findings = [
        f"{file}: privileged trigger {trigger!r} is forbidden"
        for trigger in sorted(names & PRIVILEGED_TRIGGERS)
    ]
    if entry["kind"] == "reusable":
        if names != {"workflow_call"}:
            findings.append(f"{file}: a reusable workflow exposes only workflow_call")
        return findings
    if "workflow_call" in names:
        findings.append(f"{file}: only reusable workflows may expose workflow_call")
    if not isinstance(workflow.get("concurrency"), dict):
        findings.append(f"{file}: must declare a concurrency group")
    return findings


def workflow_findings(
    entry: dict[str, Any], workflow: dict[str, Any], reusables: set[str]
) -> list[str]:
    """Check one parsed workflow against its inventory entry and policy.

    Parameters
    ----------
    entry
        Inventory entry.
    workflow
        Parsed workflow document.
    reusables
        Declared reusable workflow file names.

    Returns
    -------
    list[str]
        Workflow violations.
    """
    file = entry["file"]
    findings = []
    if workflow.get("permissions") != {}:
        findings.append(f"{file}: top-level permissions must be {{}}")
    findings.extend(_trigger_findings(entry, workflow))
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        findings.append(f"{file}: no jobs mapping")
        return findings
    if sorted(jobs) != sorted(entry["jobs"]):
        findings.append(f"{file}: jobs {sorted(jobs)} differ from declared {sorted(entry['jobs'])}")
    for name, job in jobs.items():
        findings.extend(_job_findings(file, entry["kind"], name, job, reusables))
    findings.extend(publication_findings(file, workflow))
    return findings


def _gate_findings(file: str, gate: object, call_jobs: set[str]) -> list[str]:
    """Check the aggregate gate job of the coordinator.

    Parameters
    ----------
    file
        Coordinator file name.
    gate
        Parsed gate job, or ``None`` when absent.
    call_jobs
        Names of the coordinator's reusable-call jobs.

    Returns
    -------
    list[str]
        Gate violations.
    """
    if not isinstance(gate, dict):
        return [f"{file}: aggregate gate job missing"]
    findings = []
    needs = gate.get("needs")
    if not isinstance(needs, list) or sorted(needs) != sorted(call_jobs):
        findings.append(f"{file}: gate must need every reusable call exactly once")
    if str(gate.get("if", "")).strip() != "always()":
        findings.append(f"{file}: gate must run with if: always()")
    steps = gate.get("steps")
    step_mappings = [
        step for step in (steps if isinstance(steps, list) else []) if isinstance(step, dict)
    ]
    script = "\n".join(str(step.get("run", "")) for step in step_mappings)
    environment = " ".join(str(item.get("env", "")) for item in [gate, *step_mappings])
    if (
        "needs.*.result" not in environment
        or '!= "success"' not in script
        or "exit 1" not in script
    ):
        findings.append(f"{file}: gate must fail on any non-success result")
    return findings


def coordinator_findings(
    file: str, workflow: dict[str, Any], gate_name: str, reusables: set[str]
) -> list[str]:
    """Check the coordinator's shape, reusable calls and aggregate gate.

    Parameters
    ----------
    file
        Coordinator file name.
    workflow
        Parsed coordinator document.
    gate_name
        Inventory-declared aggregate gate job.
    reusables
        Declared reusable workflow file names.

    Returns
    -------
    list[str]
        Coordinator violations.
    """
    findings = []
    extra = sorted(set(workflow) - COORDINATOR_KEYS)
    if extra:
        findings.append(f"{file}: unexpected top-level keys {extra}")
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return findings
    calls = {name: job for name, job in jobs.items() if name != gate_name}
    called = []
    for name, job in calls.items():
        reference = job.get("uses") if isinstance(job, dict) else None
        if isinstance(reference, str) and reference.startswith(LOCAL_REUSABLE_PREFIX):
            called.append(reference.removeprefix(LOCAL_REUSABLE_PREFIX))
        else:
            findings.append(f"{file}: job {name} is not a local reusable call")
    if sorted(called) != sorted(reusables):
        findings.append(
            f"{file}: calls {sorted(called)} differ from declared reusables {sorted(reusables)}"
        )
    findings.extend(_gate_findings(file, jobs.get(gate_name), set(calls)))
    return findings


def _structure_findings(inventory: dict[str, Any], present: list[str]) -> list[str]:
    """Check file declarations, taxonomy partition and coordinator naming.

    Parameters
    ----------
    inventory
        Shape-valid inventory.
    present
        Workflow file names found on disk.

    Returns
    -------
    list[str]
        Structural violations.
    """
    entries: list[dict[str, Any]] = inventory["workflows"]
    declared = [entry["file"] for entry in entries]
    findings = []
    if len(declared) != len(set(declared)):
        findings.append("inventory: a workflow file is declared more than once")
    if sorted(set(declared)) != present:
        findings.append(
            f"inventory: declared files {sorted(set(declared))} differ from tree {present}"
        )
    findings.extend(
        f"{name}: write-authority workflow is not permitted"
        for name in present
        if name in WRITE_AUTHORITY_WORKFLOWS
    )
    categories = {entry["category"] for entry in entries}
    omitted = set(inventory["omitted_categories"])
    if categories & omitted or categories | omitted != TAXONOMY:
        findings.append("inventory: declared and omitted categories must partition 1..11")
    coordinators = [entry["file"] for entry in entries if entry["kind"] == "coordinator"]
    if len(coordinators) != 1:
        findings.append("inventory: exactly one coordinator is required")
    elif {inventory["coordinator"], inventory["aggregate_gate"]["workflow"]} != set(coordinators):
        findings.append(
            "inventory: coordinator and aggregate_gate.workflow must name the coordinator file"
        )
    return findings


def audit(root: Path) -> list[str]:
    """Audit the workflow tree of one repository root.

    Parameters
    ----------
    root
        Repository root containing ``.github``.

    Returns
    -------
    list[str]
        Every violation found; empty when the tree is compliant.
    """
    try:
        inventory = load_json_object(root / INVENTORY_RELATIVE)
    except (OSError, ValueError) as exc:
        return [f"inventory unreadable: {exc}"]
    findings = inventory_findings(inventory)
    if findings:
        return findings
    workflows_dir = root / WORKFLOWS_RELATIVE
    present = (
        sorted(path.name for path in workflows_dir.iterdir() if path.suffix in {".yml", ".yaml"})
        if workflows_dir.is_dir()
        else []
    )
    findings = _structure_findings(inventory, present)
    if findings:
        return findings
    entries: list[dict[str, Any]] = inventory["workflows"]
    reusables = {entry["file"] for entry in entries if entry["kind"] == "reusable"}
    limits = inventory["size_limits"]
    for entry in entries:
        file = entry["file"]
        raw = (workflows_dir / file).read_bytes()
        if len(raw) > limits["max_bytes"]:
            findings.append(f"{file}: exceeds the byte ceiling")
        if raw.count(b"\n") > limits["max_lines"]:
            findings.append(f"{file}: exceeds the line ceiling")
        try:
            workflow = load_workflow(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            findings.append(f"{file}: {exc}")
            continue
        findings.extend(workflow_findings(entry, workflow, reusables))
        if entry["kind"] == "coordinator":
            findings.extend(
                coordinator_findings(file, workflow, inventory["aggregate_gate"]["job"], reusables)
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the guard from the command line.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when compliant, ``1`` when any violation exists.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: the repository containing this tool)",
    )
    args = parser.parse_args(argv)
    findings = audit(args.root)
    for finding in findings:
        print(f"workflow-audit: FAIL {finding}")
    if findings:
        return 1
    print("workflow-audit: PASS inventory, privilege and pinning policy verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
