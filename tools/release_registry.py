# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — registry artifacts and hosted runs of a release

"""Read a release's registry artifacts and hosted workflow runs from the public APIs.

PyPI gives the distribution files of a version, crates.io the checksum of each listed crate
publication and GitHub the hosted workflow runs of the release commit. The JSON reader is a
parameter, so a release specification is filled from recorded documents as from the live
services.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from pypi_downloads import fetch

if TYPE_CHECKING:
    from collections.abc import Callable

PACKAGE: Final = "loop-timing-witness"
"""Distribution name on PyPI and the repository name on GitHub."""


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


def pypi_artifacts(version: str, commit: str, fetch: Callable[[str], Any]) -> list[dict[str, str]]:
    """Return the PyPI distributions of a version, built from the release commit.

    Parameters
    ----------
    version
        Released package version.
    commit
        Commit the hosted publish workflow built the distributions from.
    fetch
        JSON reader of one URL.

    Returns
    -------
    list[dict[str, str]]
        PyPI files by file name.
    """
    pypi = fetch(f"https://pypi.org/pypi/{PACKAGE}/{version}/json")
    return [
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


def registry_artifacts(
    version: str, commit: str, listed: list[dict[str, str]], fetch: Callable[[str], Any]
) -> list[dict[str, str]]:
    """Return the registry artifacts of a release from the listed publications.

    Parameters
    ----------
    version
        Released package version.
    commit
        Commit the hosted publish workflow built the distributions from.
    listed
        Crate publications, each with ``crate``, ``version`` and ``note``, and
        complete earlier artifacts that name their ``registry`` and are kept
        unchanged. When one of those is a PyPI file, the release published no
        distribution of its own and PyPI is not read for its version.
    fetch
        JSON reader of one URL.

    Returns
    -------
    list[dict[str, str]]
        PyPI files of the version by file name, unless earlier ones are kept, then
        the listed entries in the given order.
    """
    kept = [item for item in listed if "registry" in item]
    artifacts = (
        []
        if any(item["registry"] == "pypi" for item in kept)
        else pypi_artifacts(version, commit, fetch)
    )
    for item in listed:
        if "registry" in item:
            artifacts.append(item)
            continue
        published = fetch(f"https://crates.io/api/v1/crates/{item['crate']}/{item['version']}")
        artifacts.append(
            {
                "registry": "crates.io",
                "crate": item["crate"],
                "version": item["version"],
                "sha256": published["version"]["checksum"],
                "note": item["note"],
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

    Raises
    ------
    ValueError
        If a run of the commit has not finished.
    """
    runs = fetch(
        f"https://api.github.com/repos/anulum/{PACKAGE}/actions/runs?head_sha={commit}&per_page=100"
    )
    unfinished = [run["html_url"] for run in runs["workflow_runs"] if run["conclusion"] is None]
    if unfinished:
        message = f"hosted runs of the commit still unfinished: {', '.join(sorted(unfinished))}"
        raise ValueError(message)
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
        Specification whose ``registry_artifacts`` lists the crate publications and
        any earlier artifacts kept unchanged.
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
