# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — release provenance builder against the published records

"""Rebuild both published release records and their ZIPs from the tagged commits."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
import release_provenance
from source_release import RELEASES

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

COMPUTED = ("schema", "prepared_at", "repository", "tag", "source_commit", "source_archive")


def published(version: str) -> dict[str, Any]:
    """Return one published release record.

    Parameters
    ----------
    version
        Registered release version.

    Returns
    -------
    dict[str, Any]
        The frozen ``release-provenance.json`` of the release.
    """
    path = REPOSITORY_ROOT / f"tests/data/source-release-v{version}-provenance.json"
    record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return record


def specification(record: dict[str, Any], version: str) -> dict[str, Any]:
    """Return the specification a published record was made from.

    Parameters
    ----------
    record
        Published record.
    version
        Its release version.

    Returns
    -------
    dict[str, Any]
        Every declared member, without the computed ones.
    """
    declared = {
        key: value for key, value in record.items() if key not in {*COMPUTED, "source_file_sha256"}
    }
    return {"schema": release_provenance.SPEC_SCHEMA, "version": version, **declared}


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
def test_published_records_rebuild_from_their_commits(tmp_path: Path, version: str) -> None:
    """Rebuild every computed member and the ZIP of both published releases.

    Parameters
    ----------
    tmp_path
        Exclusive output directory.
    version
        Registered release version.
    """
    record = published(version)
    release = RELEASES[version]
    rebuilt = release_provenance.build_record(
        REPOSITORY_ROOT,
        release.source,
        specification(record, version),
        tmp_path,
        record["prepared_at"],
    )
    # 0.2.0 recorded the archive size as a decimal string; the builder writes the integer.
    expected = {
        **record,
        "source_archive": {
            **record["source_archive"],
            "bytes": int(record["source_archive"]["bytes"]),
        },
    }
    assert rebuilt == expected
    assert rebuilt["source_archive"]["sha256"] == release.archive_sha256
    assert list(rebuilt) == list(record)


def test_command_writes_the_published_0_1_0_record_byte_for_byte(tmp_path: Path) -> None:
    """Write the 0.1.0 record, whose archive size is an integer, exactly as published.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    """
    record = published("0.1.0")
    spec = tmp_path / "specification.json"
    release_provenance.write_json(specification(record, "0.1.0"), spec)
    output = tmp_path / "release"
    output.mkdir()
    arguments = [
        "build",
        "--repository",
        str(REPOSITORY_ROOT),
        "--commit",
        RELEASES["0.1.0"].source,
    ]
    arguments += ["--specification", str(spec), "--output", str(output)]
    assert release_provenance.main([*arguments, "--prepared-at", record["prepared_at"]]) == 0
    frozen = REPOSITORY_ROOT / "tests/data/source-release-v0.1.0-provenance.json"
    assert (output / "release-provenance.json").read_bytes() == frozen.read_bytes()
    assert (output / "loop-timing-witness-0.1.0.zip").is_file()


def test_build_without_a_time_records_the_current_one(tmp_path: Path) -> None:
    """Record a timezone-aware preparation time when none is given.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    """
    spec = tmp_path / "specification.json"
    release_provenance.write_json(specification(published("0.1.0"), "0.1.0"), spec)
    arguments = [
        "build",
        "--repository",
        str(REPOSITORY_ROOT),
        "--commit",
        RELEASES["0.1.0"].source,
    ]
    assert (
        release_provenance.main(
            [*arguments, "--specification", str(spec), "--output", str(tmp_path)]
        )
        == 0
    )
    prepared = json.loads((tmp_path / "release-provenance.json").read_text())["prepared_at"]
    assert prepared.endswith("+00:00")


def responses(record: dict[str, Any], version: str) -> dict[str, Any]:
    """Return registry and workflow API documents that hold a published record's entries.

    Parameters
    ----------
    record
        Published 0.2.0 record.
    version
        Its release version.

    Returns
    -------
    dict[str, Any]
        Document by URL, each run listed twice and the PyPI files in reverse order.
    """
    pypi = [item for item in record["registry_artifacts"] if item["registry"] == "pypi"]
    crate = next(item for item in record["registry_artifacts"] if item["registry"] == "crates.io")
    runs = [
        {
            "name": run["workflow"],
            "event": run["event"],
            "conclusion": run["conclusion"],
            "html_url": run["run"],
        }
        for run in record["software_verification"]["hosted_workflows"]
    ]
    commit = record["source_commit"]
    return {
        f"https://pypi.org/pypi/loop-timing-witness/{version}/json": {
            "urls": [
                {
                    "filename": item["filename"],
                    "digests": {"sha256": item["sha256"]},
                    "url": item["url"],
                }
                for item in reversed(pypi)
            ]
        },
        f"https://crates.io/api/v1/crates/{crate['crate']}/{crate['version']}": {
            "version": {"checksum": crate["sha256"]}
        },
        "https://api.github.com/repos/anulum/loop-timing-witness/actions/runs"
        f"?head_sha={commit}&per_page=100": {"workflow_runs": runs + runs},
    }


def test_collect_reads_the_published_artifacts_and_runs(tmp_path: Path) -> None:
    """Collect the 0.2.0 artifacts and runs from API documents into the published lists.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    """
    record = published("0.2.0")
    documents = responses(record, "0.2.0")
    crate = next(item for item in record["registry_artifacts"] if item["registry"] == "crates.io")
    partial = specification(record, "0.2.0")
    partial["registry_artifacts"] = [
        {"crate": crate["crate"], "version": crate["version"], "note": crate["note"]}
    ]
    partial["software_verification"] = {
        "hardware_boundary": record["software_verification"]["hardware_boundary"]
    }
    spec = tmp_path / "specification.json"
    release_provenance.write_json(partial, spec)
    output = tmp_path / "collected.json"
    arguments = ["collect", "--commit", record["source_commit"], "--specification", str(spec)]
    assert (
        release_provenance.main([*arguments, "--output", str(output)], documents.__getitem__) == 0
    )
    assert json.loads(output.read_text()) == specification(record, "0.2.0")


def _runs_only(record: dict[str, Any], version: str) -> dict[str, Any]:
    """Return only the workflow-run document of a published record's commit.

    Parameters
    ----------
    record
        Published record.
    version
        Its release version.

    Returns
    -------
    dict[str, Any]
        The GitHub API document by URL, without any registry document.
    """
    return {
        url: document
        for url, document in responses(record, version).items()
        if url.startswith("https://api.github.com/")
    }


def test_collect_keeps_listed_artifacts_without_reading_the_registries(tmp_path: Path) -> None:
    """Keep complete earlier artifacts unchanged and read no registry for them.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    """
    record = published("0.2.0")
    partial = specification(record, "0.2.0")
    partial["software_verification"] = {
        "hardware_boundary": record["software_verification"]["hardware_boundary"]
    }
    spec = tmp_path / "specification.json"
    release_provenance.write_json(partial, spec)
    output = tmp_path / "collected.json"
    arguments = ["collect", "--commit", record["source_commit"], "--specification", str(spec)]
    documents = _runs_only(record, "0.2.0")
    assert (
        release_provenance.main([*arguments, "--output", str(output)], documents.__getitem__) == 0
    )
    collected = json.loads(output.read_text())
    assert collected["registry_artifacts"] == record["registry_artifacts"]
    assert collected == specification(record, "0.2.0")


def test_collect_refuses_unfinished_hosted_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse a commit whose hosted runs have not all finished, writing nothing.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    capsys
        Captured refusal.
    """
    record = published("0.2.0")
    documents = _runs_only(record, "0.2.0")
    (runs,) = documents.values()
    pending = {
        **runs["workflow_runs"][0],
        "conclusion": None,
        "html_url": "https://example.test/run",
    }
    runs["workflow_runs"] = [*runs["workflow_runs"], pending]
    spec = tmp_path / "specification.json"
    release_provenance.write_json(specification(record, "0.2.0"), spec)
    output = tmp_path / "collected.json"
    arguments = ["collect", "--commit", record["source_commit"], "--specification", str(spec)]
    assert (
        release_provenance.main([*arguments, "--output", str(output)], documents.__getitem__) == 1
    )
    refusal = capsys.readouterr().err
    assert "hosted runs of the commit still unfinished: https://example.test/run" in refusal
    assert not output.exists()


@pytest.mark.parametrize("body", [None, b'{"version": {"checksum": "0"}}'])
def test_fetch_json_refuses_an_unavailable_document(
    monkeypatch: pytest.MonkeyPatch, body: bytes | None
) -> None:
    """Decode an available document and refuse a missing or unavailable one.

    Parameters
    ----------
    monkeypatch
        Replaces the bounded network reader.
    body
        Reader result.
    """
    monkeypatch.setattr(release_provenance, "fetch", lambda _url: body)
    if body is None:
        with pytest.raises(ValueError, match="public document unavailable"):
            release_provenance.fetch_json("https://crates.io/api/v1/crates/x/1")
    else:
        assert release_provenance.fetch_json("https://crates.io/api/v1/crates/x/1") == json.loads(
            body
        )


@pytest.mark.parametrize("change", ["schema", "member"])
def test_specification_refuses_another_schema_or_member_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str
) -> None:
    """Refuse a specification with another schema or member set, writing nothing.

    Parameters
    ----------
    tmp_path
        Exclusive specification and output directory.
    capsys
        Captured refusal.
    change
        Changed schema or an added member.
    """
    spec = specification(published("0.1.0"), "0.1.0")
    if change == "schema":
        spec["schema"] = "other"
    else:
        spec["extra"] = True
    path = tmp_path / "specification.json"
    release_provenance.write_json(spec, path)
    arguments = ["build", "--commit", RELEASES["0.1.0"].source, "--specification", str(path)]
    assert release_provenance.main([*arguments, "--output", str(tmp_path)]) == 1
    assert "Release provenance refused" in capsys.readouterr().err
    assert not (tmp_path / "release-provenance.json").exists()


def test_tree_entries_that_are_not_files_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse a commit whose tree holds a submodule.

    Parameters
    ----------
    monkeypatch
        Replaces the Git reader with a listing holding a submodule.
    """
    listing = b"160000 commit " + b"0" * 40 + b"\tvendored\0"
    monkeypatch.setattr(release_provenance, "_git", lambda *_arguments, **_options: listing)
    with pytest.raises(ValueError, match="not a file: vendored"):
        release_provenance.file_digests(REPOSITORY_ROOT, "HEAD")


def test_an_unknown_commit_is_refused(tmp_path: Path) -> None:
    """Refuse a commit Git does not hold.

    Parameters
    ----------
    tmp_path
        Exclusive output directory.
    """
    with pytest.raises(subprocess.CalledProcessError):
        release_provenance.source_archive(REPOSITORY_ROOT, "0" * 40, "0.0.0", tmp_path)


def test_the_command_refuses_a_missing_specification(tmp_path: Path) -> None:
    """Exit with status one and a refusal when the specification cannot be read.

    Parameters
    ----------
    tmp_path
        Exclusive output directory.
    """
    result = subprocess.run(
        [
            sys.executable,
            "tools/release_provenance.py",
            "build",
            "--commit",
            RELEASES["0.1.0"].source,
            "--specification",
            str(tmp_path / "absent.json"),
            "--output",
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.startswith("Release provenance refused:")
    assert not tuple(tmp_path.iterdir())
