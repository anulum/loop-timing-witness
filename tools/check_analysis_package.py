# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native analysis package source and licence correspondence

"""Require exact packaged worker, schema, profile and reviewed dependency identities."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
import tomllib
from pathlib import Path
from typing import Final

from manifest_io import parse_json_object

PACKAGE_FILE_LIMIT: Final = 262144
PACKAGE_ROOT: Final = "analysis/rust"
WORKER_ROOT: Final = PACKAGE_ROOT + "/checker_worker/loop_timing_witness"
WORKER_NAMES: Final = ("__init__.py", "neural_checker_worker.py", "neural_checker_isolation.py")
PROFILE_ASSETS: Final = (
    "neural-selected-source-contract.json",
    "neural-selected-checker-policy.json",
    "neural-selected-checker-runtime.json",
    "neural-image-source-contract.json",
    "neural-image-checker-policy.json",
    "neural-image-checker-runtime.json",
)
RUN_FIXTURE: Final = "neural-selected-original.run.json"
PACKAGE_COPIES: Final = {
    **{f"{WORKER_ROOT}/{name}": f"src/loop_timing_witness/{name}" for name in WORKER_NAMES},
    **{
        f"{PACKAGE_ROOT}/public-data/{name}": f"src/loop_timing_witness/data/{name}"
        for name in PROFILE_ASSETS
    },
    f"{PACKAGE_ROOT}/neural-step-run.schema.json": "neural-step-run.schema.json",
    f"{PACKAGE_ROOT}/tests/data/{RUN_FIXTURE}": f"tests/data/{RUN_FIXTURE}",
}
LICENCE_SCHEMA: Final = "loop-timing-witness.analysis-dependency-licences.v1"
SELECTED_LICENCES: Final = frozenset({"MIT", "MIT AND Unicode-3.0"})


def read_package_file(path: Path) -> bytes:
    """Read one complete finite regular package file without following a final link.

    Parameters
    ----------
    path
        Original package or canonical owner file, subject to the 256 KiB limit.

    Returns
    -------
    bytes
        Complete bytes from the same nonblocking no-follow descriptor.

    Raises
    ------
    OSError
        If the selected file is unavailable or a final symlink.
    ValueError
        If it is nonregular or exceeds the package file allocation.
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            message = "analysis package input must be a regular file"
            raise ValueError(message)
        raw = stream.read(PACKAGE_FILE_LIMIT + 1)
    if len(raw) > PACKAGE_FILE_LIMIT:
        message = "analysis package input exceeds its byte allocation"
        raise ValueError(message)
    return raw


def _licence_findings(crate: Path) -> list[str]:
    """Reconcile the complete unique Cargo population and its reviewed notice body.

    Parameters
    ----------
    crate
        Actual analysis crate containing the original lock and review records.

    Returns
    -------
    list[str]
        Exact archive, selected licence, population or whole-notice contradictions.
    """
    findings = []
    lock = tomllib.loads(read_package_file(crate / "Cargo.lock").decode("utf-8"))
    policy = parse_json_object(
        read_package_file(crate / "dependency-licences.json"), "analysis licence record"
    )
    if set(policy) != {"schema_id", "packages", "notices_ref"}:
        return ["analysis licence record has unknown or missing fields"]
    if policy["schema_id"] != LICENCE_SCHEMA or not isinstance(policy["packages"], dict):
        return ["analysis licence record has an unsupported schema"]
    locked = [item for item in lock["package"] if "source" in item]
    expected = {f"{item['name']}@{item['version']}": item["checksum"] for item in locked}
    if len(expected) != len(locked):
        findings.append("analysis Cargo lock contains repeated review identities")
    packages = policy["packages"]
    if set(packages) != set(expected):
        findings.append("analysis Cargo lock and reviewed licence population differ")
    for name, entry in packages.items():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"checksum", "licence"}
            or entry["checksum"] != expected.get(name)
            or entry["licence"] not in SELECTED_LICENCES
        ):
            findings.append(f"{name}: archive or selected licence differs from its review")
    notices = read_package_file(crate / "THIRD_PARTY_NOTICES.md")
    if policy["notices_ref"] != {
        "sha256": hashlib.sha256(notices).hexdigest(),
        "byte_length": len(notices),
    }:
        findings.append("analysis third-party notices differ from the reviewed complete text")
    return findings


def audit(root: Path) -> list[str]:
    """Compare all packaged source copies and the complete reviewed Cargo lock.

    Parameters
    ----------
    root
        Actual repository candidate containing the public analysis crate.

    Returns
    -------
    list[str]
        Located source or licence drift findings, or a fixed malformed-input refusal.
        Canonical Python owners remain strictly typed and covered; exact packaged
        copies are also linted and strictly checked by the analysis build gate.
    """
    findings = []
    try:
        for copied, owner in PACKAGE_COPIES.items():
            if read_package_file(root / copied) != read_package_file(root / owner):
                findings.append(f"{copied}: bytes differ from the canonical owner {owner}")
        findings.extend(_licence_findings(root / PACKAGE_ROOT))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return ["analysis package, source correspondence or licence record is missing or invalid"]
    return findings


def main(argv: list[str] | None = None) -> int:
    """Validate the actual analysis package through its public command interface.

    Parameters
    ----------
    argv
        Optional command arguments; the default reads the process arguments.

    Returns
    -------
    int
        Zero only when every packaged source and reviewed dependency corresponds.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    findings = audit(args.root)
    for finding in findings:
        print(f"analysis-package: FAIL {finding}")
    if findings:
        return 1
    print("analysis-package: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
