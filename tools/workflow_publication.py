# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — exact authorised workflow publication boundaries

"""Bind Pages, PyPI and Scorecard write scopes to their real authorised jobs."""

from __future__ import annotations

from typing import Any, Final

PUBLICATION_JOBS: Final = {
    ("docs.yml", "deploy"): frozenset({"pages", "id-token"}),
    ("publish.yml", "publish"): frozenset({"id-token"}),
    ("publish-rust.yml", "publish"): frozenset({"id-token"}),
    ("scorecard.yml", "analysis"): frozenset({"security-events", "id-token"}),
}
MAIN: Final = "github.ref == 'refs/heads/main'"
DEPLOY: Final = MAIN + " && github.event_name != 'pull_request'"


def publication_job_findings(
    file: str, job: object, policy: tuple[str, str, str, str]
) -> list[str]:
    """Check a publication job against its exact permissions, input and identity.

    Parameters
    ----------
    file
        Exact authorised workflow filename.
    job
        Parsed publication job or missing value.
    policy
        Publication job, verified-input job, environment and main-branch condition.

    Returns
    -------
    list[str]
        Violations of the publication boundary.
    """
    findings = []
    name, dependency, environment, condition = policy
    if not isinstance(job, dict):
        return [f"{file}: authorised publication job {name!r} is missing"]
    expected = dict.fromkeys(sorted(PUBLICATION_JOBS[file, name]), "write")
    if file == "publish-rust.yml":
        expected = {"contents": "read", "actions": "read", "id-token": "write"}
    if job.get("permissions") != expected:
        findings.append(f"{file}: publication permissions must be exactly {expected}")
    needs = [dependency] if dependency else None
    if job.get("needs") != needs:
        findings.append(f"{file}: publication needs must be {needs!r}")
    if job.get("if") != condition:
        findings.append(f"{file}: publication must use the exact main-branch condition")
    actual = job.get("environment")
    if not isinstance(actual, dict) or actual.get("name") != environment:
        findings.append(f"{file}: publication environment must be {environment!r}")
    return findings


def publication_findings(file: str, workflow: dict[str, Any]) -> list[str]:
    """Refuse write jobs outside their source, build and identity boundaries.

    Parameters
    ----------
    file
        Exact inventory-declared workflow filename.
    workflow
        Parsed workflow mapping, already checked by the inventory guard.

    Returns
    -------
    list[str]
        Publication policy violations; unrelated workflows contribute none.
    """
    findings = []
    policies = {
        "docs.yml": ("deploy", "validate", "github-pages", DEPLOY),
        "publish.yml": ("publish", "build", "pypi", MAIN),
        "publish-rust.yml": ("publish", "", "crates-io", MAIN),
    }
    if file in policies:
        name = policies[file][0]
        findings.extend(publication_job_findings(file, workflow["jobs"].get(name), policies[file]))
    if file in {"publish.yml", "publish-rust.yml"}:
        if workflow.get("on") != {"workflow_dispatch": None}:
            findings.append(f"{file}: package publication permits only explicit manual dispatch")
        verification = "build" if file == "publish.yml" else "publish"
        build = workflow["jobs"].get(verification)
        if not isinstance(build, dict) or build.get("if") != MAIN:
            findings.append(f"{file}: package verification must start only from main")
    if file == "scorecard.yml":
        job = workflow["jobs"].get("analysis", {})
        if not isinstance(job, dict) or job.get("if") != MAIN:
            findings.append("scorecard.yml: public analysis must start only from main")
    return findings
