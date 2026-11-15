# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source release archive and provenance record

"""Build a release's source ZIP and its ``release-provenance.json`` from the tagged commit.

``collect`` reads the published registry artifacts and the hosted workflow runs of
the commit into a release specification. ``build`` is offline: from the commit and
the specification it writes the reproducible ZIP and the provenance record, whose
file digests, archive size and digests are computed, never declared.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from pypi_downloads import fetch

if TYPE_CHECKING:
    from collections.abc import Callable

SCHEMA: Final = "loop-timing-witness.source-release-provenance.v1"
SPEC_SCHEMA: Final = "loop-timing-witness.source-release-specification.v1"
REPOSITORY_URL: Final = "https://github.com/anulum/loop-timing-witness"
PACKAGE: Final = "loop-timing-witness"
SPEC_FIELDS: Final = (
    "version",
    "version_doi",
    "boundary",
    "physical_evidence_maturity",
    "not_qualified",
    "registry_artifacts",
    "software_verification",
)


def source_archive(repository: Path, commit: str, version: str, output: Path) -> Path:
    """Write the release ZIP of a commit as ``git archive`` makes it in the release time zone.

    Parameters
    ----------
    repository
        Repository holding the commit.
    commit
        Tagged release commit.
    version
        Release version, part of the file name and of every member's prefix.
    output
        Existing directory for the ZIP.

    Returns
    -------
    Path
        Written ``loop-timing-witness-<version>.zip``.

    Raises
    ------
    subprocess.CalledProcessError
        If Git cannot archive the commit.
    """
    archive = output / f"{PACKAGE}-{version}.zip"
    prefix = f"--prefix={PACKAGE}-{version}/"
    arguments = ["archive", "--format=zip", prefix, commit, f"--output={archive}"]
    _git(repository, arguments, environment={**os.environ, "TZ": "Europe/Zurich"})
    return archive


def archive_record(archive: Path) -> dict[str, Any]:
    """Return the file name, size and digests of a written archive.

    Parameters
    ----------
    archive
        Written source ZIP.

    Returns
    -------
    dict[str, Any]
        ``filename``, ``bytes`` as an integer, ``sha256`` and ``md5``.
    """
    raw = archive.read_bytes()
    return {
        "filename": archive.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "md5": hashlib.md5(raw, usedforsecurity=False).hexdigest(),
    }


def file_digests(repository: Path, commit: str) -> dict[str, str]:
    """Return the SHA-256 of every file of a commit's tree, by path in byte order.

    Parameters
    ----------
    repository
        Repository holding the commit.
    commit
        Tagged release commit.

    Returns
    -------
    dict[str, str]
        Digest of each blob's content, keyed by its repository path.

    Raises
    ------
    ValueError
        If the tree holds an entry that is not a file, such as a submodule.
    subprocess.CalledProcessError
        If Git cannot list or read the tree.
    """
    listing = _git(repository, ["ls-tree", "-r", "-z", commit])
    entries: list[tuple[str, str]] = []
    for item in filter(None, listing.split(b"\0")):
        header, name = item.split(b"\t", 1)
        _, kind, object_id = header.decode("ascii").split(" ")
        if kind != "blob":
            message = f"release tree entry is not a file: {name.decode()}"
            raise ValueError(message)
        entries.append((name.decode(), object_id))
    contents = _blob_contents(repository, [object_id for _, object_id in entries])
    return {
        name: hashlib.sha256(contents[object_id]).hexdigest()
        for name, object_id in sorted(entries, key=lambda entry: entry[0].encode())
    }


def _blob_contents(repository: Path, object_ids: list[str]) -> dict[str, bytes]:
    """Read the content of every listed blob through one ``git cat-file`` batch.

    Parameters
    ----------
    repository
        Repository holding the blobs.
    object_ids
        Blob object names.

    Returns
    -------
    dict[str, bytes]
        Content by object name.
    """
    request = "".join(f"{object_id}\n" for object_id in object_ids).encode("ascii")
    output = _git(repository, ["cat-file", "--batch"], request=request)
    contents: dict[str, bytes] = {}
    position = 0
    for object_id in object_ids:
        end = output.index(b"\n", position)
        size = int(output[position:end].split(b" ")[2])
        contents[object_id] = output[end + 1 : end + 1 + size]
        position = end + 2 + size
    return contents


def _git(
    repository: Path,
    arguments: list[str],
    request: bytes | None = None,
    environment: dict[str, str] | None = None,
) -> bytes:
    """Run one Git command in the repository and return its standard output.

    Parameters
    ----------
    repository
        Repository the command runs in.
    arguments
        Git arguments after ``git``.
    request
        Standard input, or ``None``.
    environment
        Complete environment, or ``None`` to inherit this process's one.

    Returns
    -------
    bytes
        Standard output.

    Raises
    ------
    subprocess.CalledProcessError
        If Git exits with a failure.
    """
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        input=request,
        env=environment,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def load_specification(path: Path) -> dict[str, Any]:
    """Read a release specification and require exactly its declared members.

    Parameters
    ----------
    path
        Specification JSON.

    Returns
    -------
    dict[str, Any]
        Specification members.

    Raises
    ------
    ValueError
        If the schema or the member set differs.
    """
    specification: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if specification.get("schema") != SPEC_SCHEMA:
        message = "release specification schema differs"
        raise ValueError(message)
    if set(specification) != {"schema", *SPEC_FIELDS}:
        message = "release specification members differ"
        raise ValueError(message)
    return specification


def build_record(
    repository: Path,
    commit: str,
    specification: dict[str, Any],
    output: Path,
    prepared_at: str,
) -> dict[str, Any]:
    """Write the release ZIP and return its provenance record.

    Parameters
    ----------
    repository
        Repository holding the commit.
    commit
        Full tagged release commit.
    specification
        Release specification from :func:`load_specification`.
    output
        Existing directory for the ZIP.
    prepared_at
        UTC time the record is prepared, in ISO 8601.

    Returns
    -------
    dict[str, Any]
        Record in the published member order.
    """
    version = specification["version"]
    archive = source_archive(repository, commit, version, output)
    return {
        "schema": SCHEMA,
        "prepared_at": prepared_at,
        "repository": REPOSITORY_URL,
        "tag": f"v{version}",
        "source_commit": commit,
        "source_archive": archive_record(archive),
        "registry_artifacts": specification["registry_artifacts"],
        "boundary": specification["boundary"],
        "physical_evidence_maturity": specification["physical_evidence_maturity"],
        "not_qualified": specification["not_qualified"],
        "source_file_sha256": file_digests(repository, commit),
        "version_doi": specification["version_doi"],
        "software_verification": specification["software_verification"],
    }


def fetch_json(url: str) -> object:
    """Read one public JSON document through the bounded HTTPS reader.

    Parameters
    ----------
    url
        HTTPS address of a registry or repository API document.

    Returns
    -------
    Any
        Decoded document.

    Raises
    ------
    ValueError
        If the document is missing, temporarily unavailable or invalid.
    OSError
        If the network transport fails.
    """
    body = fetch(url)
    if body is None:
        message = f"public document unavailable: {url}"
        raise ValueError(message)
    return json.loads(body)


def registry_artifacts(
    version: str, commit: str, crates: list[dict[str, str]], fetch: Callable[[str], Any]
) -> list[dict[str, str]]:
    """Return the PyPI distributions of a version and the listed crate publications.

    Parameters
    ----------
    version
        Released package version.
    commit
        Commit the hosted publish workflow built the distributions from.
    crates
        Crate publications, each with ``crate``, ``version`` and ``note``.
    fetch
        JSON reader of one URL.

    Returns
    -------
    list[dict[str, str]]
        PyPI files by file name, then the crates in the given order.
    """
    pypi = fetch(f"https://pypi.org/pypi/{PACKAGE}/{version}/json")
    artifacts = [
        {
            "registry": "pypi",
            "version": version,
            "filename": item["filename"],
            "sha256": item["digests"]["sha256"],
            "url": item["url"],
            "publisher_source_commit": commit,
        }
        for item in sorted(pypi["urls"], key=lambda entry: entry["filename"])
    ]
    for crate in crates:
        published = fetch(f"https://crates.io/api/v1/crates/{crate['crate']}/{crate['version']}")
        artifacts.append(
            {
                "registry": "crates.io",
                "crate": crate["crate"],
                "version": crate["version"],
                "sha256": published["version"]["checksum"],
                "note": crate["note"],
            }
        )
    return artifacts


def hosted_workflows(commit: str, fetch: Callable[[str], Any]) -> list[dict[str, str]]:
    """Return every hosted workflow run of a commit, sorted and without repeats.

    Parameters
    ----------
    commit
        Release commit.
    fetch
        JSON reader of one URL.

    Returns
    -------
    list[dict[str, str]]
        Workflow name, event, conclusion and run address of each run.
    """
    runs = fetch(
        f"https://api.github.com/repos/anulum/{PACKAGE}/actions/runs?head_sha={commit}&per_page=100"
    )
    unique = sorted(
        {
            (run["name"], run["event"], run["conclusion"], run["html_url"])
            for run in runs["workflow_runs"]
        }
    )
    return [
        {"workflow": name, "event": event, "conclusion": conclusion, "run": url}
        for name, event, conclusion, url in unique
    ]


def collect(
    specification: dict[str, Any], commit: str, fetch: Callable[[str], Any]
) -> dict[str, Any]:
    """Fill a specification's registry artifacts and hosted runs from the public APIs.

    Parameters
    ----------
    specification
        Specification whose ``registry_artifacts`` lists only the crate publications.
    commit
        Release commit.
    fetch
        JSON reader of one URL.

    Returns
    -------
    dict[str, Any]
        The specification with the complete artifacts and the hosted runs first in
        ``software_verification``.
    """
    crates = specification["registry_artifacts"]
    verification = {
        key: value
        for key, value in specification["software_verification"].items()
        if key != "hosted_workflows"
    }
    return {
        **specification,
        "registry_artifacts": registry_artifacts(specification["version"], commit, crates, fetch),
        "software_verification": {
            "hosted_workflows": hosted_workflows(commit, fetch),
            **verification,
        },
    }


def write_json(document: dict[str, Any], path: Path) -> None:
    """Write a document as two-space indented JSON with a final newline.

    Parameters
    ----------
    document
        JSON document.
    path
        Output file.
    """
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None, fetch: Callable[[str], Any] = fetch_json) -> int:
    """Collect a specification or build a release's ZIP and provenance record.

    Parameters
    ----------
    argv
        Command arguments; ``None`` reads the process arguments.
    fetch
        JSON reader of one URL, used by ``collect``.

    Returns
    -------
    int
        Zero on success, one when an input, Git or an output fails.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["collect", "build"])
    parser.add_argument("--repository", type=Path, default=Path())
    parser.add_argument("--commit", required=True)
    parser.add_argument("--specification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-at")
    args = parser.parse_args(argv)
    try:
        specification = load_specification(args.specification)
        if args.action == "collect":
            write_json(collect(specification, args.commit, fetch), args.output)
        else:
            prepared = args.prepared_at or dt.datetime.now(dt.UTC).isoformat()
            record = build_record(
                args.repository, args.commit, specification, args.output, prepared
            )
            write_json(record, args.output / "release-provenance.json")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Release provenance refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
