# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — blocking dependency audit graph controls

"""Exercise the public workflow guard on real Git trees and weakened audit jobs."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from test_audit_workflows import edit, inventory, save, tree

from audit_workflows import audit
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

__all__ = ["tree"]
AUDIT = "reusable-security-audit.yml"
COMMAND = "          cargo audit --file controllers/rust/Cargo.lock\n"


@pytest.mark.parametrize(
    "replacement",
    [
        "          cargo audit --file controllers/rust/Cargo.lock || true\n",
        "          cargo audit --file controllers/rust/Cargo.lock --ignore RUSTSEC-2020-0000\n",
        "          cargo audit --file controllers/rust/Cargo.lock --target-os linux\n",
        "          cargo audit --file controllers/rust/Cargo.lock --no-fetch\n",
        "          cargo audit --file controllers/rust/Cargo.lock --no-yanked\n",
        "",
    ],
)
def test_weakened_lock_command_fails_the_public_guard(
    tree: Path, run_tool: RunTool, replacement: str
) -> None:
    """Refuse actual audit command weakening through both Python API and CLI."""
    edit(tree, AUDIT, COMMAND, replacement)
    findings = audit(tree)
    assert "dependency audits: every lock needs one exact unconditional audit block" in findings
    result = run_tool("audit_workflows", str(tree))
    assert result.returncode == 1
    assert "dependency audits:" in result.stdout


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "      - name: Known vulnerabilities in every dependency lock\n",
            "      - name: Known vulnerabilities in every dependency lock\n        if: false\n",
        ),
        (
            "      - name: Known vulnerabilities in every dependency lock\n",
            (
                "      - name: Known vulnerabilities in every dependency lock\n"
                "        continue-on-error: true\n"
            ),
        ),
        (
            "      - name: Known vulnerabilities in every dependency lock\n",
            (
                "      - name: Known vulnerabilities in every dependency lock\n"
                "        shell: bash {0}\n"
            ),
        ),
        ("    steps:\n", "    if: false\n    steps:\n"),
        ("    steps:\n", "    continue-on-error: true\n    steps:\n"),
        ("    steps:\n", "    env:\n      CARGO_AUDIT_QUIET: true\n    steps:\n"),
        ("    steps:\n", "    defaults:\n      run:\n        shell: bash {0}\n    steps:\n"),
        ("permissions: {}\n", "permissions: {}\nenv:\n  CARGO_AUDIT_QUIET: true\n"),
        (
            "permissions: {}\n",
            "permissions: {}\ndefaults:\n  run:\n    shell: bash {0}\n",
        ),
        (
            "      - name: Install the pinned Rust toolchain and advisory auditor\n",
            (
                "      - name: Install the pinned Rust toolchain and advisory auditor\n"
                "        if: false\n"
            ),
        ),
        (
            "          cargo install cargo-audit --version 0.22.2 --locked\n",
            "          cargo install cargo-audit\n",
        ),
    ],
)
def test_skipped_audit_steps_and_inherited_overrides_are_refused(
    tree: Path, old: str, new: str
) -> None:
    """Changing step execution or inherited shell policy cannot keep an audit pass."""
    edit(tree, AUDIT, old, new)
    assert any("dependency audits:" in finding for finding in audit(tree))


@pytest.mark.parametrize("trigger", ["push", "pull_request"])
def test_event_filters_and_missing_events_are_refused(tree: Path, trigger: str) -> None:
    """Every head and pull request must reach the actual security category."""
    edit(tree, "ci.yml", f"  {trigger}:\n", f"  {trigger}:\n    paths: [docs/**]\n")
    assert "dependency audits: CI must audit unfiltered pushes and pull requests" in audit(tree)


def test_removed_security_category_cannot_pass_a_consistent_inventory(tree: Path) -> None:
    """Inventory and gate edits together still cannot remove the required security call."""
    edit(tree, "ci.yml", "  security:\n", "  audits:\n")
    edit(
        tree,
        "ci.yml",
        "needs: [static-policy, tests, security]",
        "needs: [static-policy, tests, audits]",
    )
    document = inventory(tree)
    document["workflows"][0]["jobs"] = ["audits", "gate", "static-policy", "tests"]
    save(tree, document)
    assert "dependency audits: CI security call must be exact and unconditional" in audit(tree)


def test_conditional_security_call_is_refused(tree: Path) -> None:
    """The caller cannot make audit execution depend on an expression."""
    edit(tree, "ci.yml", "  security:\n", "  security:\n    if: false\n")
    assert "dependency audits: CI security call must be exact and unconditional" in audit(tree)


@pytest.mark.parametrize("name", ["uv.lock", "go.sum", "Manifest.toml", "new/Cargo.lock"])
def test_new_lock_requires_its_actual_audit(tree: Path, name: str) -> None:
    """Untracked publishable locks already require an ecosystem or exact command."""
    path = tree / name
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPOSITORY_ROOT / "controllers/rust/Cargo.lock", path)
    assert any("dependency audits:" in finding for finding in audit(tree))


def test_advisory_configuration_cannot_silently_suppress_findings(tree: Path) -> None:
    """An actual cargo-audit suppression file needs explicit policy review."""
    directory = tree / ".cargo"
    directory.mkdir()
    (directory / "audit.toml").write_text('[advisories]\nignore = ["RUSTSEC-2020-0000"]\n')
    assert "dependency audits: advisory suppressions need an explicit reviewed policy" in audit(
        tree
    )


def test_missing_lock_surface_is_refused(tree: Path) -> None:
    """Removing every maintained lock never produces a vacuous green audit."""
    for name in (
        "controllers/rust/Cargo.lock",
        "runtime/bare_metal/rust_kernel/Cargo.lock",
        "requirements-dev.txt",
        "requirements-runtime.txt",
    ):
        (tree / name).unlink()
    assert "dependency audits: no maintained Python or Cargo locks" in audit(tree)


def test_lock_enumeration_error_fails_closed(tree: Path) -> None:
    """A real failed Git enumeration is a failed workflow guard."""
    shutil.rmtree(tree / ".git")
    assert any("cannot enumerate maintained locks" in finding for finding in audit(tree))


def test_removing_the_audit_workflow_with_consistent_inventory_is_refused(tree: Path) -> None:
    """A coherent workflow/inventory edit cannot erase the underlying audit category."""
    (tree / ".github/workflows" / AUDIT).unlink()
    edit(tree, "security-audit.yml", AUDIT, "reusable-static-policy.yml")
    path = tree / ".github/workflows/ci.yml"
    text = path.read_text()
    first = text.index("  security:\n")
    last = text.index("  gate:\n", first)
    path.write_text(text[:first] + text[last:])
    edit(tree, "ci.yml", "needs: [static-policy, tests, security]", "needs: [static-policy, tests]")
    document = inventory(tree)
    document["workflows"] = [row for row in document["workflows"] if row["file"] != AUDIT]
    document["workflows"][0]["jobs"] = ["gate", "static-policy", "tests"]
    save(tree, document)
    assert "dependency audits: reusable security audit job is missing" in audit(tree)
