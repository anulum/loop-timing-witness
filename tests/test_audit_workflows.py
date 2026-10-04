# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the workflow ownership, privilege and pinning guard

"""Contract tests for the workflow guard against the committed workflow tree and mutations of it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from audit_workflows import audit, load_workflow, main
from conftest import REPOSITORY_ROOT, RunTool

INVENTORY = Path(".github/workflow-inventory.json")
WORKFLOWS = Path(".github/workflows")
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Copy the committed workflow tree and inventory into a scratch root.

    Parameters
    ----------
    tmp_path
        Scratch directory.

    Returns
    -------
    Path
        Root of the copy.
    """
    root = tmp_path / "repository"
    shutil.copytree(REPOSITORY_ROOT / WORKFLOWS, root / WORKFLOWS)
    shutil.copyfile(REPOSITORY_ROOT / INVENTORY, root / INVENTORY)
    for name in (
        "controllers/rust/Cargo.lock",
        "runtime/bare_metal/rust_kernel/Cargo.lock",
        "requirements-dev.txt",
        "requirements-runtime.txt",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / name, target)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def edit(root: Path, name: str, old: str, new: str) -> None:
    """Replace one exact, present text fragment in a workflow file.

    Parameters
    ----------
    root
        Scratch root.
    name
        Workflow file name.
    old
        Fragment that must occur in the file.
    new
        Replacement.
    """
    path = root / WORKFLOWS / name
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def inventory(root: Path) -> dict[str, Any]:
    """Read the scratch inventory.

    Parameters
    ----------
    root
        Scratch root.

    Returns
    -------
    dict[str, Any]
        Decoded inventory.
    """
    document: dict[str, Any] = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    return document


def save(root: Path, document: dict[str, Any]) -> None:
    """Write the scratch inventory.

    Parameters
    ----------
    root
        Scratch root.
    document
        Inventory to write.
    """
    (root / INVENTORY).write_text(json.dumps(document), encoding="utf-8")


def test_committed_tree_passes_in_a_subprocess(run_tool: RunTool) -> None:
    """The committed workflows satisfy their own inventory and policy."""
    completed = run_tool("audit_workflows")
    assert completed.returncode == 0, completed.stdout
    assert (
        completed.stdout.strip()
        == "workflow-audit: PASS inventory, privilege and pinning policy verified"
    )


def test_copy_passes_and_command_line_accepts_a_root(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The unmodified copy passes when named on the command line."""
    assert main([str(tree)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_load_workflow_normalises_the_trigger_key_and_rejects_bad_documents() -> None:
    """Bare `on` becomes a string key; repeated keys, bad YAML and non-mappings fail."""
    assert load_workflow("on: push\njobs: {}\n") == {"on": "push", "jobs": {}}
    with pytest.raises(ValueError, match="found duplicate key 'jobs'"):
        load_workflow("jobs: {}\njobs: {}\n")
    with pytest.raises(ValueError, match="YAML parse failure"):
        load_workflow("jobs: [::\n")
    with pytest.raises(ValueError, match="workflow must be a YAML mapping"):
        load_workflow("- item\n")


def test_missing_inventory_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Without an inventory the guard fails and says why."""
    assert main([str(tmp_path)]) == 1
    assert "workflow-audit: FAIL inventory unreadable:" in capsys.readouterr().out


def test_inventory_shape_is_enforced(tree: Path) -> None:
    """Every top-level inventory member is checked before the tree is audited."""
    save(
        tree,
        {
            "workflows": [
                {
                    "file": "../escape.yml",
                    "kind": "coordinator",
                    "category": 1,
                    "jobs": ["a"],
                    "owner": "x",
                },
                {"kind": ["list"]},
            ]
        },
    )
    assert audit(tree) == [
        "inventory: schema must be 'loop-timing-witness.workflow-inventory.v1'",
        "inventory: schema_version must be '1.0.0'",
        "inventory: coordinator must name a workflow file",
        "inventory: size_limits needs positive integer max_bytes and max_lines",
        "inventory: omitted_categories must be a list of integers",
        "inventory: aggregate_gate needs workflow and job names",
        "inventory: workflows[0] needs exactly file, kind, category 1-11, non-empty jobs and owner",
        "inventory: workflows[1] needs exactly file, kind, category 1-11, non-empty jobs and owner",
    ]


def test_empty_workflow_list_is_refused(tree: Path) -> None:
    """An inventory without workflows cannot govern anything."""
    document = inventory(tree)
    document["workflows"] = []
    save(tree, document)
    assert audit(tree) == ["inventory: workflows must be a non-empty list"]


def test_declared_files_must_match_the_tree(tree: Path) -> None:
    """An undeclared file, a duplicate declaration and a missing directory are refused."""
    (tree / WORKFLOWS / "stray.yaml").write_text("name: stray\n", encoding="utf-8")
    document = inventory(tree)
    document["workflows"].append(dict(document["workflows"][-1]))
    save(tree, document)
    findings = audit(tree)
    assert findings[0] == "inventory: a workflow file is declared more than once"
    assert findings[1].startswith("inventory: declared files [")
    shutil.rmtree(tree / WORKFLOWS)
    assert audit(tree)[-1].endswith("differ from tree []")


def test_write_authority_workflow_is_refused(tree: Path) -> None:
    """A release workflow is refused even when declared."""
    shutil.copyfile(tree / WORKFLOWS / "docs.yml", tree / WORKFLOWS / "release.yml")
    document = inventory(tree)
    document["workflows"].append(
        {
            "category": 9,
            "file": "release.yml",
            "jobs": ["validate"],
            "kind": "standalone",
            "owner": "release",
        }
    )
    save(tree, document)
    assert audit(tree) == ["release.yml: write-authority workflow is not permitted"]


def test_taxonomy_partition_and_single_coordinator(tree: Path) -> None:
    """Categories must partition the taxonomy and exactly one coordinator must exist."""
    document = inventory(tree)
    document["omitted_categories"] = [1, 3]
    document["workflows"][1]["kind"] = "coordinator"
    save(tree, document)
    assert audit(tree) == [
        "inventory: declared and omitted categories must partition 1..11",
        "inventory: exactly one coordinator is required",
    ]


def test_coordinator_name_must_match_the_inventory(tree: Path) -> None:
    """The coordinator member and the gate workflow must name the coordinator file."""
    document = inventory(tree)
    document["aggregate_gate"]["workflow"] = "docs.yml"
    save(tree, document)
    assert audit(tree) == [
        "inventory: coordinator and aggregate_gate.workflow must name the coordinator file"
    ]


def test_size_ceilings_and_unparsable_files(tree: Path) -> None:
    """Byte and line ceilings apply to every file; an unparsable file is reported and skipped."""
    document = inventory(tree)
    document["size_limits"] = {"max_bytes": 1, "max_lines": 1}
    save(tree, document)
    (tree / WORKFLOWS / "docs.yml").write_bytes(b"\xff\n\n")
    findings = audit(tree)
    assert "docs.yml: exceeds the byte ceiling" in findings
    assert "docs.yml: exceeds the line ceiling" in findings
    assert any(finding.startswith("docs.yml: 'utf-8' codec can't decode") for finding in findings)
    assert "ci.yml: exceeds the byte ceiling" in findings


def test_top_level_policy_of_a_standalone_workflow(tree: Path) -> None:
    """Permissions, privileged triggers, workflow_call and concurrency are enforced."""
    edit(tree, "docs.yml", "permissions: {}\n", "permissions: read-all\n")
    edit(tree, "docs.yml", "  workflow_dispatch:\n", "  workflow_call:\n  pull_request_target:\n")
    edit(tree, "docs.yml", "concurrency:", "x-concurrency:")
    assert audit(tree) == [
        "docs.yml: top-level permissions must be {}",
        "docs.yml: privileged trigger 'pull_request_target' is forbidden",
        "docs.yml: only reusable workflows may expose workflow_call",
        "docs.yml: must declare a concurrency group",
    ]


def test_scalar_trigger_and_missing_jobs(tree: Path) -> None:
    """A scalar trigger is one trigger name; a workflow without jobs is refused."""
    path = tree / WORKFLOWS / "docs.yml"
    path.write_text(
        "name: Docs\non: workflow_run\npermissions: {}\nconcurrency:\n  group: g\n",
        encoding="utf-8",
    )
    assert audit(tree) == [
        "docs.yml: privileged trigger 'workflow_run' is forbidden",
        "docs.yml: no jobs mapping",
    ]


def test_reusable_workflow_exposes_only_workflow_call(tree: Path) -> None:
    """A reusable workflow with a direct trigger is refused."""
    edit(tree, "reusable-tests.yml", "on:\n  workflow_call:\n", "on:\n  workflow_call:\n  push:\n")
    assert audit(tree) == ["reusable-tests.yml: a reusable workflow exposes only workflow_call"]


def test_job_policy(tree: Path) -> None:
    """Job permissions, dependencies, timeouts, pinning and checkout credentials are enforced."""
    edit(
        tree,
        "sbom.yml",
        "      contents: read # read the lock file\n",
        "      contents: write\n      packages: write\n",
    )
    edit(tree, "sbom.yml", "    timeout-minutes: 10\n", "    timeout-minutes: 999\n    needs: []\n")
    edit(
        tree,
        "sbom.yml",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "actions/upload-artifact@v7",
    )
    edit(tree, "sbom.yml", "        with:\n          persist-credentials: false\n", "")
    assert audit(tree) == [
        "sbom.yml: job inventory: write scope 'contents' is not permitted",
        "sbom.yml: job inventory: write scope 'packages' is not permitted",
        "sbom.yml: job inventory: only the coordinator may declare needs",
        "sbom.yml: job inventory: timeout-minutes must be an integer in 1..360",
        "sbom.yml: job inventory: checkout must set persist-credentials: false",
        "sbom.yml: job inventory: action 'actions/upload-artifact@v7' is not pinned to a commit",
    ]


def test_job_shapes_images_and_local_references(tree: Path) -> None:
    """Non-mapping jobs, unpinned images, pinned images and unknown local calls are handled."""
    path = tree / WORKFLOWS / "docs.yml"
    path.write_text(
        "name: Docs\non:\n  push:\npermissions: {}\nconcurrency:\n  group: g\njobs:\n"
        "  validate:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n    permissions: {}\n"
        "    steps:\n      - run: echo\n      - uses: docker://alpine:3\n"
        f"      - uses: docker://alpine@sha256:{'0' * 64}\n"
        "      - uses: ./.github/workflows/unknown.yml\n"
        f"      - uses: {CHECKOUT}\n        with: none\n",
        encoding="utf-8",
    )
    findings = audit(tree)
    assert findings == [
        "docs.yml: jobs ['validate'] differ from declared ['deploy', 'validate']",
        "docs.yml: job validate: image 'docker://alpine:3' is not pinned by digest",
        (
            "docs.yml: job validate: './.github/workflows/unknown.yml' is not a declared "
            "reusable workflow"
        ),
        "docs.yml: job validate: checkout must set persist-credentials: false",
        "docs.yml: authorised publication job 'deploy' is missing",
    ]
    path.write_text(
        "on:\n  push:\npermissions: {}\nconcurrency:\n  group: g\njobs:\n  validate: text\n"
        "  other:\n    permissions: read-all\n    steps: not-a-list\n",
        encoding="utf-8",
    )
    assert audit(tree) == [
        "docs.yml: jobs ['other', 'validate'] differ from declared ['deploy', 'validate']",
        "docs.yml: job validate: must be a mapping",
        "docs.yml: job other: must declare a permissions mapping",
        "docs.yml: job other: timeout-minutes must be an integer in 1..360",
        "docs.yml: authorised publication job 'deploy' is missing",
    ]


def test_coordinator_contract(tree: Path) -> None:
    """Extra keys, non-local calls, missing calls and a weak gate are all refused."""
    edit(tree, "ci.yml", "name: CI\n", "name: CI\nenv:\n  STRAY: value\n")
    edit(
        tree,
        "ci.yml",
        "    uses: ./.github/workflows/reusable-tests.yml\n",
        "    uses: other/repository/.github/workflows/tests.yml@main\n",
    )
    edit(tree, "ci.yml", "    needs: [static-policy, tests, security]\n", "    needs: [tests]\n")
    edit(tree, "ci.yml", "    if: always()\n", "    if: success()\n")
    edit(tree, "ci.yml", "              exit 1\n", "              true\n")
    assert audit(tree) == [
        (
            "ci.yml: job tests: action 'other/repository/.github/workflows/tests.yml@main' "
            "is not pinned to a commit"
        ),
        "ci.yml: coverage caller must use the exact reusable and permission ceiling",
        "ci.yml: unexpected top-level keys ['env']",
        "ci.yml: job tests is not a local reusable call",
        (
            "ci.yml: calls ['reusable-security-audit.yml', 'reusable-static-policy.yml'] "
            "differ from declared reusables "
            "['reusable-security-audit.yml', 'reusable-static-policy.yml', 'reusable-tests.yml']"
        ),
        "ci.yml: gate must need every reusable call exactly once",
        "ci.yml: gate must run with if: always()",
        "ci.yml: gate must fail on any non-success result",
    ]


def test_coordinator_without_gate_or_jobs(tree: Path) -> None:
    """A missing gate is reported; a coordinator without a jobs mapping stops after its shape."""
    edit(tree, "ci.yml", "  gate:\n", "  final:\n")
    document = inventory(tree)
    document["workflows"][0]["jobs"] = ["final", "security", "static-policy", "tests"]
    save(tree, document)
    findings = audit(tree)
    assert "ci.yml: job final is not a local reusable call" in findings
    assert findings[-1] == "ci.yml: aggregate gate job missing"
    (tree / WORKFLOWS / "ci.yml").write_text(
        "on:\n  push:\npermissions: {}\nconcurrency:\n  group: g\njobs: []\n", encoding="utf-8"
    )
    assert audit(tree) == ["ci.yml: no jobs mapping"]


def test_gate_with_malformed_steps_and_non_mapping_call(tree: Path) -> None:
    """Gate steps that are not a list and call jobs that are not mappings are refused."""
    path = tree / WORKFLOWS / "ci.yml"
    path.write_text(
        "name: CI\non:\n  push:\npermissions: {}\nconcurrency:\n  group: g\njobs:\n"
        "  static-policy: text\n"
        "  tests:\n    uses: ./.github/workflows/reusable-tests.yml\n    permissions: {}\n"
        "  security:\n    uses: ./.github/workflows/reusable-security-audit.yml\n"
        "    permissions: {}\n"
        "  gate:\n    runs-on: ubuntu-24.04\n    timeout-minutes: 5\n"
        "    needs: [static-policy, tests, security]\n"
        "    if: always()\n    permissions: {}\n    steps: [text]\n",
        encoding="utf-8",
    )
    assert audit(tree) == [
        "ci.yml: job static-policy: must be a mapping",
        "ci.yml: coverage caller must use the exact reusable and permission ceiling",
        "ci.yml: job static-policy is not a local reusable call",
        (
            "ci.yml: calls ['reusable-security-audit.yml', 'reusable-tests.yml'] "
            "differ from declared reusables "
            "['reusable-security-audit.yml', 'reusable-static-policy.yml', 'reusable-tests.yml']"
        ),
        "ci.yml: gate must fail on any non-success result",
    ]
