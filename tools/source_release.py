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
from pathlib import Path
from typing import Final

SOURCE: Final = "1d12e0342d5320f62182fef41709773f3c555b50"
ASSETS: Final = {
    "loop-timing-witness-0.1.0.zip": (
        "3e0c83e09be127ef3fc30c0043c377f20dcfed3df58e70a49e9ebebdd6f7880e"
    ),
    "release-provenance.json": "adf3bf9db02b2495f5865db54e931151f28495f6b94e1fdb0c469d421740006d",
}
PREDICATE_TYPE: Final = (
    "https://github.com/anulum/loop-timing-witness/source-release-verification/v1"
)


def verify_release(assets: Path, reconstructed: Path, workflow_revision: str) -> dict[str, object]:
    """Compare downloaded assets and a fresh Git archive with the frozen release.

    Parameters
    ----------
    assets
        Directory containing the two unmodified release assets.
    reconstructed
        ZIP produced by Git from the immutable source commit and release prefix.
    workflow_revision
        Exact main commit executing the verification and signing workflow.

    Returns
    -------
    dict[str, object]
        Custom source-verification predicate, with distinct artifact and workflow revisions.

    Raises
    ------
    ValueError
        If a digest or workflow revision is invalid.
    OSError
        If an input cannot be read.
    """
    if re.fullmatch(r"[0-9a-f]{40}", workflow_revision) is None:
        message = "workflow revision must be a full lowercase Git commit"
        raise ValueError(message)
    for name, digest in ASSETS.items():
        if hashlib.sha256((assets / name).read_bytes()).hexdigest() != digest:
            message = f"release digest mismatch: {name}"
            raise ValueError(message)
    if (
        hashlib.sha256(reconstructed.read_bytes()).hexdigest()
        != ASSETS["loop-timing-witness-0.1.0.zip"]
    ):
        message = "reconstructed source archive differs from the frozen release"
        raise ValueError(message)
    return {
        "repository": "https://github.com/anulum/loop-timing-witness",
        "tag": "v0.1.0",
        "artifact_source_commit": SOURCE,
        "verification_workflow_commit": workflow_revision,
        "verification": "Published assets match frozen digests; ZIP equals a fresh git archive.",
        "asset_sha256": ASSETS,
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
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--reconstructed", type=Path, required=True)
    parser.add_argument("--workflow-revision", required=True)
    parser.add_argument("--predicate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        predicate = verify_release(args.assets, args.reconstructed, args.workflow_revision)
        args.predicate.write_text(json.dumps(predicate, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError):
        print("Source release verification failed; no signature is authorised.", file=sys.stderr)
        return 1
    print("Verified immutable source assets and reconstructed Git archive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
