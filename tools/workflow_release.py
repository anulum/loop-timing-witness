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


def release_findings(file: str, workflow: dict[str, Any]) -> list[str]:
    """Check the manually dispatched source signature workflow's job boundaries.

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
    findings = []
    if workflow.get("on") != {"workflow_dispatch": None}:
        findings.append(f"{file}: signatures permit only explicit manual dispatch")
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
