# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable source verification through the public CLI

"""Reconstruct each published source release and exercise release verification refusals."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from source_release import RELEASES, main

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

REVISION = "d1619fd44f66559c796621433e0fa39443d881df"
REFUSAL = "Source release verification failed; no signature is authorised.\n"


def archive(version: str, output: Path, timezone: str) -> None:
    """Write Git's ZIP of a release's frozen source commit with the given local timezone.

    Parameters
    ----------
    version
        Registered release version.
    output
        ZIP path to create.
    timezone
        ``TZ`` value; Git stores local DOS timestamps in ZIP entries.
    """
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--prefix=loop-timing-witness-{version}/",
            RELEASES[version].source,
            f"--output={output}",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        env={**os.environ, "TZ": timezone},
    )


@pytest.fixture(params=list(RELEASES))
def release_assets(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[str, Path]:
    """Build a real tag's archive and copy that release's actual public provenance record.

    Parameters
    ----------
    request
        Fixture request carrying the registered release version.
    tmp_path
        Exclusive test directory.

    Returns
    -------
    tuple[str, Path]
        Release version and the directory with byte-identical published assets and
        reconstruction.
    """
    version: str = request.param
    archive(version, tmp_path / f"loop-timing-witness-{version}.zip", "Europe/Zurich")
    shutil.copyfile(tmp_path / f"loop-timing-witness-{version}.zip", tmp_path / "reconstructed.zip")
    shutil.copyfile(
        REPOSITORY_ROOT / f"tests/data/source-release-v{version}-provenance.json",
        tmp_path / "release-provenance.json",
    )
    return version, tmp_path


def verify(version: str, tag_commit: str, assets: Path, revision: str, predicate: Path) -> int:
    """Run the public command entry point with every required argument.

    Parameters
    ----------
    version
        Release argument.
    tag_commit
        Commit the tag is claimed to name.
    assets
        Directory with the assets and ``reconstructed.zip``.
    revision
        Workflow revision argument.
    predicate
        Output path.

    Returns
    -------
    int
        Command status.
    """
    return main(
        [
            *("--release", version, "--tag-commit", tag_commit),
            *("--assets", str(assets), "--reconstructed", str(assets / "reconstructed.zip")),
            *("--workflow-revision", revision, "--predicate", str(predicate)),
        ]
    )


def test_published_assets_admit_the_release_predicate(
    release_assets: tuple[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Real assets yield a predicate naming this tag, its source and the measured digests."""
    version, assets = release_assets
    output = assets / "predicate.json"
    assert verify(version, RELEASES[version].source, assets, REVISION, output) == 0
    names = (f"loop-timing-witness-{version}.zip", "release-provenance.json")
    assert json.loads(output.read_text()) == {
        "repository": "https://github.com/anulum/loop-timing-witness",
        "tag": f"v{version}",
        "artifact_source_commit": RELEASES[version].source,
        "verification_workflow_commit": REVISION,
        "verification": "Published assets match frozen digests; ZIP equals a fresh git archive.",
        "asset_sha256": {
            name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in names
        },
        "scope": "Source asset verification, not retrospective SLSA build provenance.",
    }
    assert capsys.readouterr().out == (
        "Verified immutable source assets and reconstructed Git archive.\n"
    )


def test_utc_reconstruction_differs_only_in_zip_timestamps(
    release_assets: tuple[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """A host-timezone archive has the same members but cannot authorise a signature."""
    version, assets = release_assets
    archive(version, assets / "reconstructed.zip", "UTC")
    with (
        ZipFile(assets / f"loop-timing-witness-{version}.zip") as published,
        ZipFile(assets / "reconstructed.zip") as reconstructed,
    ):
        assert published.comment == reconstructed.comment == RELEASES[version].source.encode()
        assert published.namelist() == reconstructed.namelist()
        assert all(
            published.read(name) == reconstructed.read(name) for name in published.namelist()
        )
        assert published.infolist()[0].date_time != reconstructed.infolist()[0].date_time
    output = assets / "predicate.json"
    assert verify(version, RELEASES[version].source, assets, REVISION, output) == 1
    assert not output.exists()
    assert capsys.readouterr().err == REFUSAL


@pytest.mark.parametrize(
    "case",
    [
        "archive",
        "manifest",
        "reconstructed",
        "missing",
        "revision",
        "output",
        "tag",
        "unregistered",
    ],
)
def test_source_asset_refusal(
    release_assets: tuple[str, Path], case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Damaged files, a moved tag, an unknown release or bad identity fail closed."""
    version, assets = release_assets
    output, revision, tag_commit = assets / "predicate.json", REVISION, RELEASES[version].source
    if case in {"archive", "manifest", "reconstructed"}:
        path = (
            assets
            / {
                "archive": f"loop-timing-witness-{version}.zip",
                "manifest": "release-provenance.json",
                "reconstructed": "reconstructed.zip",
            }[case]
        )
        path.write_bytes(path.read_bytes() + b"tampered")
    if case == "missing":
        (assets / "release-provenance.json").unlink()
    if case == "revision":
        revision = "main"
    if case == "output":
        output.mkdir()
    if case == "tag":
        tag_commit = next(r.source for v, r in RELEASES.items() if v != version)
    if case == "unregistered":
        version = "9.9.9"
    assert verify(version, tag_commit, assets, revision, output) == 1
    assert not output.is_file()
    assert capsys.readouterr().err == REFUSAL


@pytest.mark.parametrize("version", list(RELEASES))
def test_frozen_registry_matches_each_release_record(version: str) -> None:
    """Each byte-exact provenance fixture names the registered tag, commit and archive digest."""
    path = REPOSITORY_ROOT / f"tests/data/source-release-v{version}-provenance.json"
    release = RELEASES[version]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == release.provenance_sha256
    record = json.loads(path.read_text())
    assert (record["tag"], record["source_commit"]) == (f"v{version}", release.source)
    assert record["source_archive"]["filename"] == f"loop-timing-witness-{version}.zip"
    assert record["source_archive"]["sha256"] == release.archive_sha256


def test_public_command_runs_without_input_files(tmp_path: Path) -> None:
    """The standalone tool returns a fixed refusal without leaking OS exception text."""
    source = RELEASES["0.2.0"].source
    result = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "tools/source_release.py",
            *("--release", "0.2.0", "--tag-commit", source, "--assets", str(tmp_path)),
            *("--reconstructed", str(tmp_path / "absent.zip"), "--workflow-revision", source),
            *("--predicate", str(tmp_path / "predicate.json")),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode, result.stdout, result.stderr) == (1, "", REFUSAL)
