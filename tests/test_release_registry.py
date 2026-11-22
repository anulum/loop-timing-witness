# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — registry artifacts and hosted runs of a release

"""Read registry artifacts and hosted runs from recorded API documents."""

from __future__ import annotations

import json
from typing import Any

import pytest
import release_registry

COMMIT = "a" * 40
PYPI = "https://pypi.org/pypi/loop-timing-witness/9.9.9/json"
CRATE = "https://crates.io/api/v1/crates/witness-controller/9.9.9"
RUNS = (
    "https://api.github.com/repos/anulum/loop-timing-witness/actions/runs"
    f"?head_sha={COMMIT}&per_page=100"
)


def _run(name: str, conclusion: str | None, url: str) -> dict[str, Any]:
    """Return one workflow run as the GitHub API lists it.

    Parameters
    ----------
    name
        Workflow name.
    conclusion
        Run conclusion, ``None`` while the run is unfinished.
    url
        Run address.

    Returns
    -------
    dict[str, Any]
        The run's listed members.
    """
    return {"name": name, "event": "push", "conclusion": conclusion, "html_url": url}


def _documents() -> dict[str, Any]:
    """Return PyPI, crates.io and GitHub documents of one release, by URL.

    Returns
    -------
    dict[str, Any]
        PyPI files out of name order and each run listed twice.
    """
    wheel = {"filename": "w.whl", "digests": {"sha256": "1" * 64}, "url": "https://x.test/w"}
    sdist = {"filename": "s.tar.gz", "digests": {"sha256": "2" * 64}, "url": "https://x.test/s"}
    runs = [_run("CI", "success", "https://x.test/ci"), _run("Docs", "success", "https://x.test/d")]
    return {
        PYPI: {"urls": [wheel, sdist]},
        CRATE: {"version": {"checksum": "3" * 64}},
        RUNS: {"workflow_runs": [runs[1], runs[0], runs[1]]},
    }


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
    monkeypatch.setattr(release_registry, "fetch", lambda _url: body)
    if body is None:
        with pytest.raises(ValueError, match="public document unavailable"):
            release_registry.fetch_json("https://crates.io/api/v1/crates/x/1")
    else:
        assert release_registry.fetch_json("https://crates.io/api/v1/crates/x/1") == json.loads(
            body
        )


def test_pypi_files_are_listed_by_name_with_their_publishing_commit() -> None:
    """Every PyPI file of the version is recorded with its digest, address and commit."""
    artifacts = release_registry.pypi_artifacts("9.9.9", COMMIT, _documents().__getitem__)
    assert [item["filename"] for item in artifacts] == ["s.tar.gz", "w.whl"]
    assert artifacts[0] == {
        "registry": "pypi",
        "version": "9.9.9",
        "filename": "s.tar.gz",
        "sha256": "2" * 64,
        "url": "https://x.test/s",
        "publisher_source_commit": COMMIT,
    }


def test_crate_publications_follow_the_pypi_files() -> None:
    """A listed crate publication takes its checksum from crates.io, after the PyPI files."""
    listed = [{"crate": "witness-controller", "version": "9.9.9", "note": "core"}]
    artifacts = release_registry.registry_artifacts(
        "9.9.9", COMMIT, listed, _documents().__getitem__
    )
    assert [item["registry"] for item in artifacts] == ["pypi", "pypi", "crates.io"]
    assert artifacts[-1] == {
        "registry": "crates.io",
        "crate": "witness-controller",
        "version": "9.9.9",
        "sha256": "3" * 64,
        "note": "core",
    }


def test_kept_pypi_artifacts_are_not_read_again() -> None:
    """Earlier complete artifacts stay as listed, and PyPI is not read for the version."""
    earlier = {"registry": "pypi", "version": "9.9.8", "filename": "old.whl"}
    documents = {url: document for url, document in _documents().items() if url != PYPI}
    listed = [earlier, {"crate": "witness-controller", "version": "9.9.9", "note": "core"}]
    artifacts = release_registry.registry_artifacts("9.9.9", COMMIT, listed, documents.__getitem__)
    assert artifacts[0] is earlier
    assert [item["registry"] for item in artifacts] == ["pypi", "crates.io"]


def test_hosted_runs_are_sorted_without_repeats() -> None:
    """Each listed run appears once, ordered by workflow name and address."""
    runs = release_registry.hosted_workflows(COMMIT, _documents().__getitem__)
    assert runs == [
        {"workflow": "CI", "event": "push", "conclusion": "success", "run": "https://x.test/ci"},
        {"workflow": "Docs", "event": "push", "conclusion": "success", "run": "https://x.test/d"},
    ]


def test_unfinished_hosted_runs_are_refused_by_address() -> None:
    """A run without a conclusion refuses the collection and names every such run."""
    documents = _documents()
    documents[RUNS]["workflow_runs"] += [
        _run("SBOM", None, "https://x.test/z"),
        _run("CodeQL", None, "https://x.test/a"),
    ]
    with pytest.raises(ValueError, match=r"unfinished: https://x\.test/a, https://x\.test/z$"):
        release_registry.hosted_workflows(COMMIT, documents.__getitem__)


def test_collection_puts_the_hosted_runs_first_and_keeps_every_other_member() -> None:
    """Collected runs replace earlier ones and lead the verification; other members stay."""
    specification = {
        "schema": "s",
        "version": "9.9.9",
        "registry_artifacts": [{"crate": "witness-controller", "version": "9.9.9", "note": "c"}],
        "software_verification": {"hosted_workflows": ["stale"], "hardware_boundary": "none"},
        "boundary": "b",
    }
    collected = release_registry.collect(specification, COMMIT, _documents().__getitem__)
    assert list(collected["software_verification"]) == ["hosted_workflows", "hardware_boundary"]
    assert collected["software_verification"]["hardware_boundary"] == "none"
    assert len(collected["software_verification"]["hosted_workflows"]) == 2
    assert len(collected["registry_artifacts"]) == 3
    assert {key: collected[key] for key in ("schema", "version", "boundary")} == {
        "schema": "s",
        "version": "9.9.9",
        "boundary": "b",
    }
