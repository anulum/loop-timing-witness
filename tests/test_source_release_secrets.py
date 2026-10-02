# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public digest recognition keeps credential scanning active

"""Run the actual secret scanner against the frozen manifest and refused mutations."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("case", ["original", "changed-digest", "other-path", "api-field"])
def test_public_digest_recognition_is_exact(tmp_path: Path, case: str) -> None:
    """Only exact public hash lines in the one frozen fixture are recognised."""
    relative = "tests/data/source-release-v0.1.0-provenance.json"
    text = (REPOSITORY_ROOT / relative).read_text()
    value = json.loads(text)
    digest = value["source_file_sha256"]["controllers/rust/tests/controller_api.rs"]
    if case == "changed-digest":
        text = text.replace(digest, digest[::-1])
    if case == "other-path":
        relative = "tests/data/other.json"
    if case == "api-field":
        text += '\napi_key = "' + digest + '"\n'
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(text)
    report = tmp_path.parent / (tmp_path.name + "-scanner-report.json")
    result = subprocess.run(
        [
            "gitleaks",
            "dir",
            "--config",
            str(REPOSITORY_ROOT / ".gitleaks.toml"),
            "--redact=100",
            "--report-format=json",
            "--report-path",
            str(report),
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (0 if case == "original" else 1), result.stderr
    findings = json.loads(report.read_text())
    assert len(findings) == (0 if case == "original" else 15 if case == "other-path" else 1)
    assert digest not in result.stdout + result.stderr
