# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — committed lock audits inside the required CI graph

"""Bind every maintained dependency lock to literal, blocking advisory commands."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from repository_files import candidate_files

if TYPE_CHECKING:
    from pathlib import Path

AUDIT_WORKFLOW: Final = "reusable-security-audit.yml"
UNSUPPORTED_LOCK_NAMES: Final = frozenset(
    {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.sum", "Manifest.toml"}
)
CARGO_AUDIT_INSTALL: Final = "cargo install cargo-audit --version 0.22.2 --locked"
# The components named by rust-toolchain.toml are installed with the toolchain;
# adding them to a minimal toolchain on first use has failed on hosted runners.
RUST_TOOLCHAIN_INSTALL: Final = (
    "rustup toolchain install 1.99.0 --profile minimal --component rustfmt --component clippy"
)


def lock_commands(names: list[str]) -> tuple[list[str], list[str]]:
    """Build mandatory commands and list lock ecosystems without a registered auditor.

    Parameters
    ----------
    names
        Complete publishable Git file list.

    Returns
    -------
    tuple[list[str], list[str]]
        Exact audit commands and unsupported lock paths.
    """
    locks = []
    unsupported = []
    for name in names:
        base = PurePosixPath(name).name
        if base == "Cargo.lock" or (base.startswith("requirements-") and base.endswith(".txt")):
            locks.append(name)
        elif base.endswith(".lock") or base in UNSUPPORTED_LOCK_NAMES:
            unsupported.append(name)
    commands = [
        f"cargo audit --file {name}"
        if name.endswith("Cargo.lock")
        else f".venv/bin/pip-audit --require-hashes --disable-pip -r {name}"
        for name in locks
    ]
    return commands, unsupported


def dependency_audit_findings(root: Path, workflows: dict[str, dict[str, Any]]) -> list[str]:
    """Check the real workflow graph and complete publishable lock surface.

    Parameters
    ----------
    root
        Git work tree containing the maintained locks.
    workflows
        Parsed and structurally validated workflow documents.

    Returns
    -------
    list[str]
        Missing audits, softened commands, unsupported locks or skipped CI paths.
    """
    try:
        names = candidate_files(root)
    except RuntimeError as exc:
        return [f"dependency audits: cannot enumerate maintained locks: {exc}"]
    commands, unsupported = lock_commands(names)
    findings = []
    if unsupported:
        findings.append(f"dependency audits: unsupported lock ecosystems {unsupported}")
    if not commands:
        return [*findings, "dependency audits: no maintained Python or Cargo locks"]
    security = workflows.get(AUDIT_WORKFLOW, {})
    job = security.get("jobs", {}).get("audit", {})
    if not job:
        return [*findings, "dependency audits: reusable security audit job is missing"]
    if {"env", "defaults"} & security.keys() or {
        "if",
        "continue-on-error",
        "env",
        "defaults",
        "strategy",
    } & job.keys():
        findings.append("dependency audits: audit workflow/job must have no skipping or overrides")
    steps = job.get("steps", [])
    audit_steps = [
        step
        for step in steps
        if isinstance(step, dict) and str(step.get("run", "")).splitlines() == commands
    ]
    if len(audit_steps) != 1 or set(audit_steps[0]) != {"name", "run"}:
        findings.append("dependency audits: every lock needs one exact unconditional audit block")
    installation_steps = [
        step
        for step in steps
        if isinstance(step, dict) and CARGO_AUDIT_INSTALL in str(step.get("run", "")).splitlines()
    ]
    if (
        len(installation_steps) != 1
        or set(installation_steps[0]) != {"name", "run"}
        or str(installation_steps[0]["run"]).splitlines()
        != [
            RUST_TOOLCHAIN_INSTALL,
            "rustup default 1.99.0",
            CARGO_AUDIT_INSTALL,
            'test "$(cargo-audit --version)" = "cargo-audit 0.22.2"',
        ]
    ):
        findings.append("dependency audits: cargo-audit installation must keep its exact pin")
    if (root / ".cargo/audit.toml").exists():
        findings.append("dependency audits: advisory suppressions need an explicit reviewed policy")
    findings.extend(audit_call_findings(workflows))
    return findings


def audit_call_findings(workflows: dict[str, dict[str, Any]]) -> list[str]:
    """Require an unfiltered coordinator and unconditional security call.

    Parameters
    ----------
    workflows
        Structurally validated workflow documents.

    Returns
    -------
    list[str]
        Event filters or absent/conditional audit calls.
    """
    findings = []
    coordinator = workflows.get("ci.yml", {})
    triggers = coordinator.get("on", {})
    if not isinstance(triggers, dict) or any(
        trigger not in triggers or triggers[trigger] not in (None, {})
        for trigger in ("push", "pull_request")
    ):
        findings.append("dependency audits: CI must audit unfiltered pushes and pull requests")
    caller = coordinator.get("jobs", {}).get("security", {})
    if (
        caller.get("uses") != f"./.github/workflows/{AUDIT_WORKFLOW}"
        or {"if", "continue-on-error"} & caller.keys()
    ):
        findings.append("dependency audits: CI security call must be exact and unconditional")
    return findings
