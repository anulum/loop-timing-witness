# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — authorised workflow publication policy tests

"""Exercise real workflow definitions and refused mutations through the guard CLI."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
import yaml

from audit_workflows import load_workflow, main
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def publication_tree(tmp_path: Path) -> Path:
    """Copy the actual workflow tree and ownership inventory.

    Parameters
    ----------
    tmp_path
        Exclusive test directory.

    Returns
    -------
    Path
        Repository snapshot containing the complete real workflow surface.
    """
    root = tmp_path / "repository"
    shutil.copytree(REPOSITORY_ROOT / ".github/workflows", root / ".github/workflows")
    shutil.copyfile(
        REPOSITORY_ROOT / ".github/workflow-inventory.json",
        root / ".github/workflow-inventory.json",
    )
    return root


def test_authorised_publication_tree_passes(
    publication_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Actual Pages, PyPI and Scorecard jobs satisfy their narrow permissions."""
    assert main([str(publication_tree)]) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.parametrize(
    "case",
    [
        ("docs.yml", "deploy", "permissions", {"contents": "write"}, "publication permissions"),
        ("docs.yml", "deploy", "needs", [], "publication needs"),
        ("docs.yml", "deploy", "if", "always()", "exact main-branch condition"),
        ("docs.yml", "deploy", "environment", "github-pages", "publication environment"),
        ("docs.yml", "deploy", "environment", {"name": "other"}, "publication environment"),
        ("publish.yml", "publish", "permissions", {}, "publication permissions"),
        ("publish.yml", "publish", "needs", ["unverified"], "publication needs"),
        ("publish.yml", "publish", "if", "always()", "exact main-branch condition"),
        ("publish.yml", "publish", "environment", {}, "publication environment"),
        ("publish.yml", "build", "if", "always()", "verification must start only from main"),
        ("scorecard.yml", "analysis", "if", "always()", "analysis must start only from main"),
        ("docs.yml", "validate", "permissions", {"id-token": "write"}, "is not permitted"),
        ("scorecard.yml", "analysis", "needs", ["validate"], "only the coordinator"),
    ],
)
def test_publication_boundary_mutations_are_refused(
    publication_tree: Path,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, str, str, object, str],
) -> None:
    """Wrong source, privilege, prerequisite or environment fails on the real workflow."""
    file, job, field, value, finding = case
    path = publication_tree / ".github/workflows" / file
    workflow = load_workflow(path.read_text())
    workflow["jobs"][job][field] = value
    path.write_text(yaml.safe_dump(workflow))
    assert main([str(publication_tree)]) == 1
    assert finding in capsys.readouterr().out


@pytest.mark.parametrize(
    ("file", "job"),
    [("docs.yml", "deploy"), ("publish.yml", "publish")],
)
def test_missing_publication_job_is_refused(
    publication_tree: Path, capsys: pytest.CaptureFixture[str], file: str, job: str
) -> None:
    """Removing an authorised writer cannot leave an apparently valid publication surface."""
    path = publication_tree / ".github/workflows" / file
    workflow = load_workflow(path.read_text())
    del workflow["jobs"][job]
    path.write_text(yaml.safe_dump(workflow))
    assert main([str(publication_tree)]) == 1
    assert "authorised publication job" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("file", "job", "finding"),
    [
        ("publish.yml", "build", "verification must start only from main"),
        ("scorecard.yml", "analysis", "analysis must start only from main"),
    ],
)
def test_malformed_verification_job_is_refused(
    publication_tree: Path, capsys: pytest.CaptureFixture[str], file: str, job: str, finding: str
) -> None:
    """A non-mapping job produces a policy failure rather than crashing the guard."""
    path = publication_tree / ".github/workflows" / file
    workflow = load_workflow(path.read_text())
    workflow["jobs"][job] = "unverified"
    path.write_text(yaml.safe_dump(workflow))
    assert main([str(publication_tree)]) == 1
    assert finding in capsys.readouterr().out


def test_package_publication_cannot_become_automatic(
    publication_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adding a push trigger refuses the otherwise valid manually dispatched publisher."""
    path = publication_tree / ".github/workflows/publish.yml"
    workflow = load_workflow(path.read_text())
    workflow["on"]["push"] = {"branches": ["main"]}
    path.write_text(yaml.safe_dump(workflow))
    assert main([str(publication_tree)]) == 1
    assert "only explicit manual dispatch" in capsys.readouterr().out
