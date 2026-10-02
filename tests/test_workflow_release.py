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


def test_signature_dispatch_cannot_become_automatic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A source push cannot automatically acquire a signing certificate or release writer."""
    shutil.copytree(REPOSITORY_ROOT / ".github/workflows", tmp_path / ".github/workflows")
    shutil.copyfile(
        REPOSITORY_ROOT / ".github/workflow-inventory.json",
        tmp_path / ".github/workflow-inventory.json",
    )
    path = tmp_path / ".github/workflows/source-release-signatures.yml"
    document = load_workflow(path.read_text())
    document["on"] = {"push": None}
    path.write_text(yaml.safe_dump(document))
    assert main([str(tmp_path)]) == 1
    assert "signatures permit only explicit manual dispatch" in capsys.readouterr().out
