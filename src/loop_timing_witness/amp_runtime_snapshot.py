# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — captured original compiler and simulator runtime libraries

"""Preserve actual runtime library bytes and their original receipt bindings."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator

from .manifest_io import canonical_json_bytes, load_json_object, sha256_of_file

HASH_SCHEMA = {
    "type": "object",
    "minProperties": 1,
    "propertyNames": {"type": "string", "pattern": "^/"},
    "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
}


def runtime_index(identities: object) -> dict[str, dict[str, str]]:
    """Assign stable run-local paths to a validated original runtime library identity map.

    Parameters
    ----------
    identities
        Original absolute library paths and SHA-256 values from compiler or simulator admission.

    Returns
    -------
    dict of str to dict of str to str
        Original path mapped to its captured relative path and expected original hash.

    Raises
    ------
    ValueError
        If the original identity map is empty or its paths/hashes have invalid types or shapes.
    """
    if not Draft202012Validator(HASH_SCHEMA).is_valid(identities):
        message = "AMP runtime library identities are invalid"
        raise ValueError(message)
    hashes = cast("dict[str, str]", identities)
    return {
        name: {"path": f"runtime_sources/{index:04d}/library", "sha256": digest}
        for index, (name, digest) in enumerate(sorted(hashes.items()))
    }


def snapshot_runtime(output: Path, identities: object) -> None:
    """Exclusively copy original loader-resolved libraries and verify their hash readback.

    Parameters
    ----------
    output
        Original new image or capture directory.
    identities
        Original admitted compiler or actual simulator runtime library map.

    Raises
    ------
    OSError
        If original files or exclusive destinations are unavailable.
    ValueError
        If original library bytes changed between admission and copying.
    """
    index = runtime_index(identities)
    (output / "runtime_sources").mkdir()
    for name, item in index.items():
        target = output / item["path"]
        target.parent.mkdir()
        with target.open("xb") as stream:
            stream.write(Path(name).read_bytes())
        if sha256_of_file(target) != item["sha256"]:
            message = "AMP runtime library changed during snapshot"
            raise ValueError(message)
    with (output / "runtime_source_index.json").open("xb") as stream:
        stream.write(canonical_json_bytes(index))


def validate_runtime_snapshot(output: Path, identities: object) -> None:
    """Require exact original identity/index agreement and unchanged captured library bytes.

    Parameters
    ----------
    output
        Original completed image or simulator capture directory.
    identities
        Original compiler or simulator runtime library map from its retained receipt.

    Raises
    ------
    OSError
        If captured original index or library files are unavailable.
    ValueError
        If the captured index, original hash binding or contained file paths disagree.
    """
    index = load_json_object(output / "runtime_source_index.json")
    if index != runtime_index(identities):
        message = "AMP runtime library snapshot index disagrees with original identities"
        raise ValueError(message)
    root = output.resolve()
    for item in index.values():
        path = output / item["path"]
        if not path.resolve().is_relative_to(root) or sha256_of_file(path) != item["sha256"]:
            message = "AMP captured runtime library bytes or paths changed"
            raise ValueError(message)
