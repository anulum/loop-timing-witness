# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the development dependency licence guard

"""Contract tests for the lock-to-licence-record guard and its expression parser."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from check_dependency_licences import (
    DEFAULT_POLICY,
    audit,
    expression_identifiers,
    locked_pins,
    main,
    normalise_name,
)
from conftest import REPOSITORY_ROOT, RunTool

if TYPE_CHECKING:
    from pathlib import Path

LOCK = (
    "alpha-tool==1.0.0 \\\n"
    "    --hash=sha256:" + "a" * 64 + "\n"
    "    # via -r requirements-dev.in\n"
    "Beta_Lib==2.1 \\\n"
    "    --hash=sha256:" + "b" * 64 + "\n"
)


def policy_document(**overrides: object) -> dict[str, Any]:
    """Build a licence record that matches ``LOCK``.

    Parameters
    ----------
    **overrides
        Top-level members to replace.

    Returns
    -------
    dict[str, Any]
        Licence record.
    """
    document: dict[str, Any] = {
        "allowed_licences": ["Apache-2.0", "MIT"],
        "lock_file": "requirements-dev.txt",
        "packages": {
            "alpha-tool": {"licence": "MIT", "version": "1.0.0"},
            "beta-lib": {"licence": "(MIT OR Apache-2.0)", "version": "2.1"},
        },
        "schema": "loop-timing-witness.dependency-licences.v1",
        "schema_version": "1.0.0",
    }
    document.update(overrides)
    return document


def write_case(tmp_path: Path, document: dict[str, Any], lock: str = LOCK) -> Path:
    """Write a licence record and its lock into a scratch directory.

    Parameters
    ----------
    tmp_path
        Scratch directory.
    document
        Licence record.
    lock
        Lock file text.

    Returns
    -------
    Path
        Path of the licence record.
    """
    (tmp_path / "requirements-dev.txt").write_text(lock, encoding="utf-8")
    path = tmp_path / "licences.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_committed_record_matches_the_committed_lock_in_a_subprocess(run_tool: RunTool) -> None:
    """Every pinned development package has exactly one reviewed licence record."""
    completed = run_tool("check_dependency_licences")
    assert completed.returncode == 0, completed.stdout
    assert completed.stdout.strip() == "dependency-licences: PASS"
    assert DEFAULT_POLICY == REPOSITORY_ROOT / "development-dependency-licences.json"


def test_committed_record_covers_every_lock_pin() -> None:
    """The committed record and lock have identical package sets and versions."""
    record = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))["packages"]
    pins = locked_pins((REPOSITORY_ROOT / "requirements-dev.txt").read_text(encoding="utf-8"))
    assert {name: entry["version"] for name, entry in record.items()} == pins


def test_matching_case_passes(tmp_path: Path) -> None:
    """A record that matches its lock with allowed licences has no findings."""
    assert audit(write_case(tmp_path, policy_document())) == []


def test_pins_are_read_with_normalised_names() -> None:
    """Pins are keyed by the normalised name; continuation and comment lines are ignored."""
    assert locked_pins(LOCK) == {"alpha-tool": "1.0.0", "beta-lib": "2.1"}
    assert normalise_name("Zope.Interface__Extra") == "zope-interface-extra"


def test_duplicate_pin_is_refused(tmp_path: Path) -> None:
    """A lock that pins one package twice under two spellings is unreadable."""
    findings = audit(write_case(tmp_path, policy_document(), LOCK + "alpha_tool==1.0.1\n"))
    assert findings == ["lock unreadable: lock pins alpha-tool more than once"]


def test_missing_lock_is_refused(tmp_path: Path) -> None:
    """A record whose lock file does not exist fails."""
    path = tmp_path / "licences.json"
    path.write_text(json.dumps(policy_document()), encoding="utf-8")
    findings = audit(path)
    assert len(findings) == 1
    assert findings[0].startswith("lock unreadable:")


def test_record_and_lock_disagreements_are_reported(tmp_path: Path) -> None:
    """Unrecorded pins, unpinned records, version drift and spelling are each reported."""
    packages = {
        "alpha-tool": {"licence": "MIT", "version": "0.9.0"},
        "Gamma_Pkg": {"licence": "MIT", "version": "3.0"},
        "delta": {"licence": "MIT", "version": "4.0"},
    }
    findings = audit(write_case(tmp_path, policy_document(packages=packages)))
    assert findings == [
        "Gamma_Pkg: record name must be written in normalised form 'gamma-pkg'",
        "beta-lib: pinned but has no licence record",
        "delta: licence record without a pin",
        "alpha-tool: record version 0.9.0 differs from pin 1.0.0",
    ]


def test_disallowed_and_malformed_licences_are_reported(tmp_path: Path) -> None:
    """An identifier outside the allow-list and a broken expression are findings."""
    packages = {
        "alpha-tool": {"licence": "GPL-3.0-only", "version": "1.0.0"},
        "beta-lib": {"licence": "MIT AND", "version": "2.1"},
    }
    findings = audit(write_case(tmp_path, policy_document(packages=packages)))
    assert findings == [
        "alpha-tool: licence 'GPL-3.0-only' is not in allowed_licences",
        "beta-lib: malformed licence expression 'MIT AND'",
    ]


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (
            {"schema": "other", "schema_version": "9"},
            [
                "policy: schema must be 'loop-timing-witness.dependency-licences.v1'",
                "policy: schema_version must be '1.0.0'",
                "policy: lock_file must be a relative path",
                "policy: allowed_licences must be a non-empty list of identifiers",
                "policy: packages must map names to {licence, version} strings",
            ],
        ),
        (
            policy_document(allowed_licences=[], packages={"x": {"licence": "MIT"}}),
            [
                "policy: allowed_licences must be a non-empty list of identifiers",
                "policy: packages must map names to {licence, version} strings",
            ],
        ),
    ],
)
def test_malformed_record_is_refused(
    tmp_path: Path, document: dict[str, Any], expected: list[str]
) -> None:
    """A record of the wrong shape is refused before it is compared."""
    assert audit(write_case(tmp_path, document)) == expected


def test_unreadable_record_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A missing record fails through the command line."""
    assert main([str(tmp_path / "absent.json")]) == 1
    assert "dependency-licences: FAIL policy unreadable:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("expression", "identifiers"),
    [
        ("MIT", ["MIT"]),
        ("MIT OR Apache-2.0", ["MIT", "Apache-2.0"]),
        ("Apache-2.0 AND (MIT OR BSD-3-Clause)", ["Apache-2.0", "MIT", "BSD-3-Clause"]),
        ("GPL-2.0-or-later WITH Classpath-exception-2.0", ["GPL-2.0-or-later"]),
        ("((MIT))", ["MIT"]),
        ("LicenseRef-Vendor.1+ AND ISC", ["LicenseRef-Vendor.1+", "ISC"]),
    ],
)
def test_expression_identifiers_of_valid_expressions(
    expression: str, identifiers: list[str]
) -> None:
    """Valid expressions yield their licence identifiers in order, without exceptions."""
    assert expression_identifiers(expression) == identifiers


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "AND MIT",
        "MIT MIT",
        "(MIT",
        "MIT)",
        "()",
        "MIT WITH",
        "MIT WITH (X)",
        "MIT WITH OR",
        "WITH X",
        "MIT OR",
    ],
)
def test_expression_identifiers_refuse_malformed_expressions(expression: str) -> None:
    """Every grammar violation raises the malformed-expression error."""
    with pytest.raises(ValueError, match="malformed licence expression"):
        expression_identifiers(expression)


def test_expression_identifiers_refuse_foreign_characters() -> None:
    """Characters outside the grammar are named in the error."""
    with pytest.raises(ValueError, match=r"unexpected characters '/,' in 'MIT/Apache-2.0,'"):
        expression_identifiers("MIT/Apache-2.0,")
