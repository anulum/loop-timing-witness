# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable source verification through the public CLI

"""Reconstruct the actual published source and exercise release verification refusals."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from source_release import SOURCE, main

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def release_assets(tmp_path: Path) -> Path:
    """Build the real tag's archive and copy the actual public provenance record.

    Parameters
    ----------
    tmp_path
        Exclusive test directory.

    Returns
    -------
    Path
        Directory with byte-identical published source assets and reconstruction.
    """
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            "--prefix=loop-timing-witness-0.1.0/",
            SOURCE,
            f"--output={tmp_path / 'loop-timing-witness-0.1.0.zip'}",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    shutil.copyfile(tmp_path / "loop-timing-witness-0.1.0.zip", tmp_path / "reconstructed.zip")
    shutil.copyfile(
        REPOSITORY_ROOT / "tests/data/source-release-v0.1.0-provenance.json",
        tmp_path / "release-provenance.json",
    )
    return tmp_path


@pytest.mark.parametrize(
    "case", ["valid", "archive", "manifest", "reconstructed", "missing", "revision", "output"]
)
def test_source_asset_admission_and_refusal(
    release_assets: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Real assets pass; damaged files, bad identity and unwritable output fail closed."""
    output = release_assets / "predicate.json"
    revision = "d1619fd44f66559c796621433e0fa39443d881df"
    if case in {"archive", "manifest", "reconstructed"}:
        name = {
            "archive": "loop-timing-witness-0.1.0.zip",
            "manifest": "release-provenance.json",
            "reconstructed": "reconstructed.zip",
        }[case]
        path = release_assets / name
        path.write_bytes(path.read_bytes() + b"tampered")
    if case == "missing":
        (release_assets / "release-provenance.json").unlink()
    if case == "revision":
        revision = "main"
    if case == "output":
        output.mkdir()
    status = main(
        [
            "--assets",
            str(release_assets),
            "--reconstructed",
            str(release_assets / "reconstructed.zip"),
            "--workflow-revision",
            revision,
            "--predicate",
            str(output),
        ]
    )
    if case == "valid":
        assert status == 0
        predicate = json.loads(output.read_text())
        assert predicate["artifact_source_commit"] == SOURCE
        assert predicate["verification_workflow_commit"] == revision
        assert len(predicate["asset_sha256"]) == 2
        assert "not retrospective SLSA" in predicate["scope"]
        assert "Verified immutable" in capsys.readouterr().out
    else:
        assert status == 1
        assert not output.is_file()
        assert capsys.readouterr().err == (
            "Source release verification failed; no signature is authorised.\n"
        )


def test_public_command_runs_without_input_files(tmp_path: Path) -> None:
    """The standalone tool returns a fixed refusal without leaking OS exception text."""
    result = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "tools/source_release.py",
            "--assets",
            str(tmp_path),
            "--reconstructed",
            str(tmp_path / "absent.zip"),
            "--workflow-revision",
            SOURCE,
            "--predicate",
            str(tmp_path / "predicate.json"),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "verification failed" in result.stderr
    assert "Traceback" not in result.stderr
