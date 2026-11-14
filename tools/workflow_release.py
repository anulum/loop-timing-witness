# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source signature identity and privilege boundaries

"""Constrain source verification, OIDC signing and release attachment to separate jobs."""

from __future__ import annotations

from typing import Any

from source_release import RELEASES

DISPATCH_INPUT: dict[str, object] = {
    "description": "Published source release to verify and sign",
    "required": True,
    "type": "choice",
    "options": list(RELEASES),
}


def dispatch_findings(file: str, trigger: object) -> list[str]:
    """Require manual dispatch with exactly the registered release choice.

    Parameters
    ----------
    file
        Workflow filename used in findings.
    trigger
        Parsed ``on`` value.

    Returns
    -------
    list[str]
        At most one violation.
    """
    if not isinstance(trigger, dict) or set(trigger) != {"workflow_dispatch"}:
        return [f"{file}: signatures permit only explicit manual dispatch"]
    if trigger["workflow_dispatch"] != {"inputs": {"release": DISPATCH_INPUT}}:
        return [f"{file}: dispatch must offer exactly the registered source releases"]
    return []


def release_findings(file: str, workflow: dict[str, Any]) -> list[str]:
    """Check the source signature workflow's dispatch input and job boundaries.

    The only trigger is a manual dispatch whose single required choice input
    offers exactly the releases registered in ``source_release.RELEASES``.

    Parameters
    ----------
    file
        Inventory-declared workflow filename.
    workflow
        Parsed workflow with a jobs mapping.

    Returns
    -------
    list[str]
        Violations; unrelated workflow definitions contribute none.
    """
    if file != "source-release-signatures.yml":
        return []
    findings = dispatch_findings(file, workflow.get("on"))
    policies = {
        "verify": ({"contents": "read", "actions": "read"}, None, None),
        "sign": (
            {"contents": "read", "id-token": "write", "attestations": "write"},
            ["verify"],
            {"name": "source-signatures"},
        ),
        "publish": ({"contents": "write"}, ["sign"], {"name": "source-signatures"}),
    }
    for name, (permissions, needs, environment) in policies.items():
        job = workflow["jobs"].get(name)
        if not isinstance(job, dict):
            findings.append(f"{file}: signature job {name!r} is missing or malformed")
            continue
        expected = {
            "permissions": permissions,
            "needs": needs,
            "environment": environment,
            "if": "github.ref == 'refs/heads/main'",
        }
        for field, value in expected.items():
            if job.get(field) != value:
                findings.append(f"{file}: {name} must have exact {field} {value!r}")
    return findings
