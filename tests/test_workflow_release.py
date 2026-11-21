# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source signature workflow policy regression tests

"""Exercise source signature privilege mutations through the real workflow auditor."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
import yaml
from source_release import RELEASES
from workflow_release import DISPATCH_INPUT

from audit_workflows import load_workflow, main
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("job", ["verify", "sign", "publish"])
@pytest.mark.parametrize(
    "field", ["permissions", "needs", "environment", "if", "missing", "malformed"]
)
def test_signature_jobs_reject_privilege_mutations(
    tmp_path: Path, job: str, field: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Read-only verification, separate signing and narrow publishing are mandatory."""
    shutil.copytree(REPOSITORY_ROOT / ".github/workflows", tmp_path / ".github/workflows")
    shutil.copyfile(
        REPOSITORY_ROOT / ".github/workflow-inventory.json",
        tmp_path / ".github/workflow-inventory.json",
    )
    path = tmp_path / ".github/workflows/source-release-signatures.yml"
    document = load_workflow(path.read_text())
    if field == "missing":
        del document["jobs"][job]
    elif field == "malformed":
        document["jobs"][job] = "unverified"
    else:
        document["jobs"][job][field] = {
            "permissions": {"contents": "write", "id-token": "write"},
            "needs": ["unverified"],
            "environment": "other",
            "if": "always()",
        }[field]
    path.write_text(yaml.safe_dump(document))
    assert main([str(tmp_path)]) == 1
    assert "source-release-signatures.yml:" in capsys.readouterr().out


FAILURE = "workflow-audit: FAIL source-release-signatures.yml: "


def mutated_trigger(tmp_path: Path, trigger: dict[str, object]) -> int:
    """Audit a copy of the real workflows whose signature trigger is replaced.

    Parameters
    ----------
    tmp_path
        Exclusive repository copy root.
    trigger
        Replacement ``on`` mapping.

    Returns
    -------
    int
        Workflow auditor status.
    """
    shutil.copytree(REPOSITORY_ROOT / ".github/workflows", tmp_path / ".github/workflows")
    shutil.copyfile(
        REPOSITORY_ROOT / ".github/workflow-inventory.json",
        tmp_path / ".github/workflow-inventory.json",
    )
    path = tmp_path / ".github/workflows/source-release-signatures.yml"
    document = load_workflow(path.read_text())
    document["on"] = trigger
    path.write_text(yaml.safe_dump(document))
    return main([str(tmp_path)])


def finding_lines(output: str) -> list[str]:
    """Return the auditor's report lines that name the signature workflow."""
    return [line for line in output.splitlines() if "source-release-signatures.yml:" in line]


@pytest.mark.parametrize("trigger", [{"push": None}, {"workflow_dispatch": None, "push": None}])
def test_signature_dispatch_cannot_become_automatic(
    tmp_path: Path, trigger: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """A source push cannot automatically acquire a signing certificate or release writer."""
    assert mutated_trigger(tmp_path, trigger) == 1
    assert finding_lines(capsys.readouterr().out) == [
        f"{FAILURE}signatures permit only explicit manual dispatch"
    ]


@pytest.mark.parametrize("change", ["unregistered", "missing", "free-text", "optional", "none"])
def test_signature_dispatch_offers_exactly_the_registered_releases(
    tmp_path: Path, change: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The release input is a required choice whose options equal the frozen registry."""
    release = dict(DISPATCH_INPUT)
    if change == "unregistered":
        release["options"] = [*RELEASES, "9.9.9"]
    if change == "missing":
        release["options"] = list(RELEASES)[:-1]
    if change == "free-text":
        release["type"] = "string"
    if change == "optional":
        release["required"] = False
    dispatch = None if change == "none" else {"inputs": {"release": release}}
    assert mutated_trigger(tmp_path, {"workflow_dispatch": dispatch}) == 1
    assert finding_lines(capsys.readouterr().out) == [
        f"{FAILURE}dispatch must offer exactly the registered source releases"
    ]


def test_signature_dispatch_registry_is_the_committed_workflow_input() -> None:
    """The committed workflow offers the registry's releases in registry order."""
    path = REPOSITORY_ROOT / ".github/workflows/source-release-signatures.yml"
    trigger = load_workflow(path.read_text())["on"]
    assert trigger == {"workflow_dispatch": {"inputs": {"release": DISPATCH_INPUT}}}
    assert trigger["workflow_dispatch"]["inputs"]["release"]["options"] == [
        "0.1.0",
        "0.2.0",
        "0.3.0",
        "0.4.0",
    ]
