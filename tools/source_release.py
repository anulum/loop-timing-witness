# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable source release verification

"""Verify the published source assets before signing a source-verification predicate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PREDICATE_TYPE: Final = (
    "https://github.com/anulum/loop-timing-witness/source-release-verification/v1"
)


@dataclass(frozen=True)
class Release:
    """One published source release: its tagged commit and the digests of its two assets.

    Parameters
    ----------
    source
        Full commit the release tag names and the source archive was made from.
    archive_sha256
        SHA-256 of the published source ZIP.
    provenance_sha256
        SHA-256 of the published ``release-provenance.json``.
    """

    source: str
    archive_sha256: str
    provenance_sha256: str


RELEASES: Final = {
    "0.1.0": Release(
        source="1d12e0342d5320f62182fef41709773f3c555b50",
        archive_sha256="3e0c83e09be127ef3fc30c0043c377f20dcfed3df58e70a49e9ebebdd6f7880e",
        provenance_sha256="adf3bf9db02b2495f5865db54e931151f28495f6b94e1fdb0c469d421740006d",
    ),
    "0.2.0": Release(
        source="1ced8822a947a2dd7a5d5e9376187b0fa36620f6",
        archive_sha256="40acb25fc2777b81a00e8b2b985359ce62a962f1966577067d1d8040ebe35ea8",
        provenance_sha256="24884ee3278864032d97854e1f8bdc77d4edceb8a98c4408e8e534553c6e83bb",
    ),
}


def asset_digests(version: str) -> dict[str, str]:
    """Return the frozen digest of each published asset of one release.

    Parameters
    ----------
    version
        Registered release version.

    Returns
    -------
    dict[str, str]
        SHA-256 by asset filename, the source ZIP first.
    """
    release = RELEASES[version]
    return {
        f"loop-timing-witness-{version}.zip": release.archive_sha256,
        "release-provenance.json": release.provenance_sha256,
    }


def release_identity(version: str, tag_commit: str, workflow_revision: str) -> Release:
    """Return a registered release whose tag and signing workflow identities are acceptable.

    Parameters
    ----------
    version
        Requested release version.
    tag_commit
        Commit the repository's ``v<version>`` tag names.
    workflow_revision
        Exact main commit executing the verification and signing workflow.

    Returns
    -------
    Release
        The frozen registry entry.

    Raises
    ------
    ValueError
        If the version is unregistered, the workflow revision is not a full commit or the tag
        names another commit than the frozen source.
    """
    if version not in RELEASES:
        message = f"unregistered release: {version}"
        raise ValueError(message)
    if re.fullmatch(r"[0-9a-f]{40}", workflow_revision) is None:
        message = "workflow revision must be a full lowercase Git commit"
        raise ValueError(message)
    release = RELEASES[version]
    if tag_commit != release.source:
        message = "release tag names another commit than the frozen source"
        raise ValueError(message)
    return release


def verify_release(
    version: str, tag_commit: str, assets: Path, reconstructed: Path, workflow_revision: str
) -> dict[str, object]:
    """Compare a release's downloaded assets and a fresh Git archive with its frozen digests.

    Parameters
    ----------
    version
        Registered release version.
    tag_commit
        Commit the repository's ``v<version>`` tag names.
    assets
        Directory containing the two unmodified release assets.
    reconstructed
        ZIP produced by Git from the tagged commit and the release prefix.
    workflow_revision
        Exact main commit executing the verification and signing workflow.

    Returns
    -------
    dict[str, object]
        Custom source-verification predicate, with distinct artifact and workflow revisions.

    Raises
    ------
    ValueError
        If an identity is refused by :func:`release_identity` or a digest differs.
    OSError
        If an input cannot be read.
    """
    release = release_identity(version, tag_commit, workflow_revision)
    digests = asset_digests(version)
    for name, digest in digests.items():
        if hashlib.sha256((assets / name).read_bytes()).hexdigest() != digest:
            message = f"release digest mismatch: {name}"
            raise ValueError(message)
    if hashlib.sha256(reconstructed.read_bytes()).hexdigest() != release.archive_sha256:
        message = "reconstructed source archive differs from the frozen release"
        raise ValueError(message)
    return {
        "repository": "https://github.com/anulum/loop-timing-witness",
        "tag": f"v{version}",
        "artifact_source_commit": release.source,
        "verification_workflow_commit": workflow_revision,
        "verification": "Published assets match frozen digests; ZIP equals a fresh git archive.",
        "asset_sha256": digests,
        "scope": "Source asset verification, not retrospective SLSA build provenance.",
    }


def main(argv: list[str] | None = None) -> int:
    """Write a verified predicate or refuse without creating an output.

    Parameters
    ----------
    argv
        Command arguments; ``None`` reads the process arguments.

    Returns
    -------
    int
        Zero for verified assets, one for an input or output failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--tag-commit", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--reconstructed", type=Path, required=True)
    parser.add_argument("--workflow-revision", required=True)
    parser.add_argument("--predicate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        predicate = verify_release(
            args.release, args.tag_commit, args.assets, args.reconstructed, args.workflow_revision
        )
        args.predicate.write_text(json.dumps(predicate, indent=2) + "\n", encoding="utf-8")
    except ValueError, OSError:
        print("Source release verification failed; no signature is authorised.", file=sys.stderr)
        return 1
    print("Verified immutable source assets and reconstructed Git archive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
