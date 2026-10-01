# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repository-level contract tests

"""Repository-level contract tests: the scaffold stays complete, pinned and truthful."""

from __future__ import annotations

import json
import re
import tomllib

import pytest

from check_commit_trailers import SUPERLATIVE
from check_dependency_licences import locked_pins
from conftest import REPOSITORY_ROOT
from manifest_io import load_json_object, sha256_of_file
from preflight import ACTIONLINT_MODULE, GITLEAKS_MODULE, TYPOS_VERSION
from repository_files import candidate_files

REQUIRED_FILES = (
    ".editorconfig",
    ".gitattributes",
    ".github/CODEOWNERS",
    ".github/FUNDING.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    ".github/workflow-inventory.json",
    ".github/workflows/ci.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/docs.yml",
    ".github/workflows/pre-commit.yml",
    ".github/workflows/sbom.yml",
    ".github/workflows/scorecard.yml",
    ".github/workflows/security-audit.yml",
    ".github/zizmor.yml",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".zenodo.json",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "CONTRIBUTORS.md",
    "GOVERNANCE.md",
    "LICENSE",
    "LICENSES/AGPL-3.0-or-later.txt",
    "Makefile",
    "NOTICE.md",
    "README.md",
    "REUSE.toml",
    "ROADMAP.md",
    "SECURITY.md",
    "SUPPORT.md",
    "VALIDATION.md",
    "capability-inventory.json",
    "development-dependency-licences.json",
    "docs/ARCHITECTURE.md",
    "docs/MEASUREMENT_PROTOCOL.md",
    "docs/THREAT_MODEL.md",
    "docs/adr/0001-repository-boundary.md",
    "measurement-domain.json",
    "measurement-domain.schema.json",
    "papers/README.md",
    "papers/submissions/README.md",
    "pyproject.toml",
    "requirements-dev.in",
    "requirements-dev.txt",
    "tools/preflight.py",
)
FORBIDDEN_PATHS = (
    ".coordination",
    ".env",
    "04_ARCANE_SAPIENCE",
    "AGENTS.md",
    "ARCHIVE",
    "BACKUP",
)
UNEARNED_BADGE_MARKERS = (
    "api.reuse.software/badge/",
    "bestpractices.dev/projects/",
    "zenodo.org/badge/",
)
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"


def publishable_text(relative: str) -> str:
    """Read one publishable repository file as text.

    Parameters
    ----------
    relative
        Path relative to the repository root.

    Returns
    -------
    str
        File content.
    """
    return (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", REQUIRED_FILES)
def test_required_file_exists_with_content(relative: str) -> None:
    """Every Tier-0 surface exists as a non-empty, repository-owned regular file."""
    path = REPOSITORY_ROOT / relative
    assert path.is_file(), relative
    assert not path.is_symlink(), relative
    assert path.stat().st_size > 0, relative


@pytest.mark.parametrize("relative", FORBIDDEN_PATHS)
def test_forbidden_path_is_absent(relative: str) -> None:
    """Agent state, backups, archives and environment files never exist in the repository."""
    assert not (REPOSITORY_ROOT / relative).exists(), relative


def test_ignore_rules_keep_private_and_backup_trees_out() -> None:
    """The ignore file carries the defensive and private-content lines, without re-includes."""
    lines = {line.strip() for line in publishable_text(".gitignore").splitlines()}
    for required in (
        "/BACKUP/",
        "/ARCHIVE/",
        "/.coordination/",
        "/04_ARCANE_SAPIENCE/",
        "docs/internal/",
        "docs/internal/**",
        ".venv/",
    ):
        assert required in lines, required
    assert not [line for line in lines if line.startswith("!")]


def test_public_surfaces_carry_no_unearned_evidence_claims() -> None:
    """Published software metadata stays aligned without unearned hardware or DOI claims."""
    readme = publishable_text("README.md")
    for marker in UNEARNED_BADGE_MARKERS:
        assert marker not in readme, marker
    changelog = publishable_text("CHANGELOG.md")
    project = tomllib.loads(publishable_text("pyproject.toml"))["project"]
    crate = tomllib.loads(publishable_text("controllers/rust/Cargo.toml"))["package"]
    version = project["version"]
    assert crate["version"] == version
    assert re.findall(r"^## \[(.+?)\]", changelog, flags=re.MULTILINE) == ["Unreleased", version]
    citation = publishable_text("CITATION.cff")
    zenodo = load_json_object(REPOSITORY_ROOT / ".zenodo.json")
    assert re.findall(r"^version: (.+)$", citation, flags=re.MULTILINE) == [version]
    released = re.findall(r"^date-released: (.+)$", citation, flags=re.MULTILINE)
    assert released == [zenodo["publication_date"]]
    assert f"## [{version}] - {released[0]}" in changelog
    assert zenodo["version"] == version
    assert not re.search(r"^doi:", citation, flags=re.MULTILINE)
    assert "doi" not in zenodo
    assert "No DOI has been assigned" in readme
    assert "No registry release" not in citation
    assert f"| `{version}` | yes" in publishable_text("SECURITY.md")
    badges = re.findall(r"\[!\[([^]]+)\]\(([^)]+)\)\]\(([^)]+)\)", readme)
    assert [(label, target) for label, _, target in badges] == [
        ("Sponsor", "https://github.com/sponsors/anulum"),
        ("PyPI", "https://pypi.org/project/loop-timing-witness/"),
        ("crates.io", "https://crates.io/crates/witness-controller"),
        ("CI", "https://github.com/anulum/loop-timing-witness/actions/workflows/ci.yml"),
        (
            "OpenSSF Scorecard",
            "https://scorecard.dev/viewer/?uri=github.com/anulum/loop-timing-witness",
        ),
    ]
    assert "https://img.shields.io/pypi/v/loop-timing-witness.svg" in readme
    assert "https://img.shields.io/crates/v/witness-controller.svg" in readme
    assert (
        "https://api.scorecard.dev/projects/github.com/anulum/loop-timing-witness/badge" in readme
    )


def test_manifest_and_inventory_state_architecture_only() -> None:
    """The manifest and its generated inventory agree on an empty, unmeasured state."""
    manifest = load_json_object(REPOSITORY_ROOT / "measurement-domain.json")
    inventory = load_json_object(REPOSITORY_ROOT / "capability-inventory.json")
    assert manifest["evidence_maturity"] == inventory["evidence_maturity"] == "architecture_only"
    assert (
        manifest["capabilities"]
        == manifest["claims"]
        == inventory["capabilities"]
        == inventory["claims"]
        == []
    )
    assert manifest["target_platform"]["verified_on_hardware"] is False
    assert manifest["design_contracts"]["status"] == "planned"
    assert inventory["source"]["manifest_sha256"] == sha256_of_file(
        REPOSITORY_ROOT / "measurement-domain.json"
    )


def test_lock_contains_every_top_level_requirement_with_hashes() -> None:
    """Each top-level pin appears identically in the lock, and every lock entry is hashed."""
    top_level = locked_pins(publishable_text("requirements-dev.in"))
    lock_text = publishable_text("requirements-dev.txt")
    pins = locked_pins(lock_text)
    assert {name: pins.get(name) for name in top_level} == top_level
    entries = re.split(r"^(?=[A-Za-z0-9][A-Za-z0-9._-]*==)", lock_text, flags=re.MULTILINE)[1:]
    assert len(entries) == len(pins)
    assert all("--hash=sha256:" in entry for entry in entries)


def test_workflows_share_one_exact_toolchain_matching_the_local_pins() -> None:
    """Python, Go and Go-built tool versions agree across workflows and the preflight runner."""
    texts = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
    }
    python_versions = {
        version
        for text in texts.values()
        for version in re.findall(r'python-version: "([^"]+)"', text)
    }
    go_versions = {
        version for text in texts.values() for version in re.findall(r'go-version: "([^"]+)"', text)
    }
    assert python_versions == {"3.13.15"}
    assert go_versions == {"1.27.1"}
    installs = {
        install for text in texts.values() for install in re.findall(r"go install (\S+)", text)
    }
    assert installs == {
        f"github.com/rhysd/actionlint/cmd/actionlint@{ACTIONLINT_MODULE[1]}",
        f"{GITLEAKS_MODULE[0]}@{GITLEAKS_MODULE[1]}",
    }
    pins = locked_pins(publishable_text("requirements-dev.txt"))
    assert f"typos-cli {pins['typos']}" == TYPOS_VERSION
    pre_commit = publishable_text(".pre-commit-config.yaml")
    assert f"# frozen: {GITLEAKS_MODULE[1]}" in pre_commit
    assert f"# frozen: v{pins['typos']}" in pre_commit
    assert f"# frozen: v{pins['reuse']}" in pre_commit


def test_pre_commit_hook_repositories_are_commit_pinned() -> None:
    """Every upstream hook repository is pinned to a 40-hexadecimal commit with its tag recorded."""
    revisions = re.findall(
        r"^\s+rev: (\S+)(.*)$", publishable_text(".pre-commit-config.yaml"), flags=re.MULTILINE
    )
    assert len(revisions) == 4
    for revision, comment in revisions:
        assert re.fullmatch(r"[0-9a-f]{40}", revision), revision
        assert re.fullmatch(r" # frozen: v\d+\.\d+\.\d+", comment), comment


def test_funding_metadata_is_the_ecosystem_payload() -> None:
    """The sponsorship file lists exactly the approved destinations in order."""
    lines = [
        line
        for line in publishable_text(".github/FUNDING.yml").splitlines()
        if line and not line.startswith("#")
    ]
    assert lines == [
        "github: anulum",
        "buy_me_a_coffee: anulum",
        "custom:",
        '  - "https://buy.stripe.com/4gM00kbiMdjAberaYz5J601"',
        '  - "https://www.paypal.com/donate?hosted_button_id=4X5F6DNT934HY"',
        '  - "https://go.twint.ch/1/e/tw?tw=acq.lJTAypb8SL2s8vPg7fL0ubi2C220ajOH0BEQn1aKfEJIiIakLpt8jlEv8XdQ9tCp."',
        '  - "https://anulum.li/contact.html"',
    ]


def test_publishable_text_uses_no_self_applied_quality_terms() -> None:
    """Outward wording stays factual; only the guard that bans the terms and its test name them."""
    exempt = {
        "tools/check_commit_trailers.py",
        "tests/test_check_commit_trailers.py",
        "docs/assets/loop-timing-witness.webp",
    }
    offenders = {}
    for relative in candidate_files(REPOSITORY_ROOT):
        if (
            relative in exempt
            or relative.startswith("LICENSE")
            or relative == "requirements-dev.txt"
            or relative.endswith(".pdf")
        ):
            continue
        found = sorted(
            {match.group(0).lower() for match in SUPERLATIVE.finditer(publishable_text(relative))}
        )
        if found:
            offenders[relative] = found
    assert offenders == {}


def test_licence_record_lists_the_lock_file_and_json_is_reuse_annotated() -> None:
    """The licence record points at the lock, and every JSON document is annotated in REUSE.toml."""
    record = json.loads(publishable_text("development-dependency-licences.json"))
    assert record["lock_file"] == "requirements-dev.txt"
    reuse = publishable_text("REUSE.toml")
    json_files = [name for name in candidate_files(REPOSITORY_ROOT) if name.endswith(".json")]
    assert json_files
    for name in json_files:
        assert f'"{name}"' in reuse, name
