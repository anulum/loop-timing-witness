# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original firmware compiler dependency closure

"""Freeze and reconcile real firmware preprocessing dependencies with portable source snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from .amp_build_dependencies import dependency_hashes
from .manifest_io import canonical_json_bytes, load_json_object, sha256_of_file

RECORD_COUNT = 5
HASH_SCHEMA = {
    "type": "object",
    "minProperties": 1,
    "propertyNames": {"type": "string", "pattern": "^(/|source/|contract\\.c$)"},
    "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
}


def image_dependency_hashes(records: tuple[Path, ...], directory: Path) -> dict[str, str]:
    """Normalize compiler-recorded image paths while preserving absolute system header identities.

    Parameters
    ----------
    records
        Actual complete GCC dependency records.
    directory
        Actual compiler working directory, also the original image root.

    Returns
    -------
    dict of str to str
        Relative image source names and absolute external dependency names with original hashes.
    """
    root = directory.resolve()
    identities = dependency_hashes(records, root)
    return {
        str(Path(name).relative_to(root)) if Path(name).is_relative_to(root) else name: digest
        for name, digest in identities.items()
    }


def dependency_index(identities: object) -> dict[str, dict[str, str]]:
    """Validate original compiler identities and assign contained portable source snapshot names.

    Parameters
    ----------
    identities
        Original relative image source or absolute external header identities.

    Returns
    -------
    dict of str to dict of str to str
        Original source names mapped to captured paths and original hashes.

    Raises
    ------
    ValueError
        If identities are missing, malformed or contain escaping relative paths.
    """
    if not Draft202012Validator(HASH_SCHEMA).is_valid(identities):
        message = "AMP original firmware dependency identities are invalid"
        raise ValueError(message)
    hashes = cast("dict[str, str]", identities)
    if any(".." in Path(name).parts for name in hashes):
        message = "AMP original firmware dependency paths escape their source root"
        raise ValueError(message)
    return {
        name: {"path": f"compiler_sources/{index:04d}/source", "sha256": digest}
        for index, (name, digest) in enumerate(sorted(hashes.items()))
    }


def snapshot_image_dependencies(directory: Path, identities: object) -> None:
    """Retain exact real preprocessing source/header bytes before any object is compiled.

    Parameters
    ----------
    directory
        New original firmware image directory.
    identities
        Original complete actual preprocessing dependency identities.

    Raises
    ------
    OSError
        If original source/header files or exclusive destinations are unavailable.
    ValueError
        If original bytes drift between preprocessing admission and copying.
    """
    index = dependency_index(identities)
    (directory / "compiler_sources").mkdir()
    for name, item in index.items():
        source = Path(name) if Path(name).is_absolute() else directory / name
        target = directory / item["path"]
        target.parent.mkdir()
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
        if sha256_of_file(target) != item["sha256"]:
            message = "AMP original firmware dependency changed during snapshot"
            raise ValueError(message)
    with (directory / "compiler_source_index.json").open("xb") as stream:
        stream.write(canonical_json_bytes(index))


def validate_image_dependency_snapshot(directory: Path, identities: object) -> None:
    """Verify the original compiler source index and all contained captured dependency bytes.

    Parameters
    ----------
    directory
        Original or captured firmware image directory.
    identities
        Original preparation's complete preprocessing dependency identities.

    Raises
    ------
    OSError
        If the original captured index or dependency files are unavailable.
    ValueError
        If index, captured paths or original byte identities disagree.
    """
    index = load_json_object(directory / "compiler_source_index.json")
    if index != dependency_index(identities):
        message = "AMP original firmware dependency snapshot index disagrees"
        raise ValueError(message)
    root = directory.resolve()
    for item in index.values():
        path = directory / item["path"]
        if not path.resolve().is_relative_to(root) or sha256_of_file(path) != item["sha256"]:
            message = "AMP captured firmware dependency bytes or paths changed"
            raise ValueError(message)


def image_dependency_record_count(data: dict[str, Any]) -> int:
    """Select the complete C/assembly closure for the original explicit arithmetic backend.

    Parameters
    ----------
    data
        Original preparation receipt; absent backend retains the five-unit C contract.

    Returns
    -------
    int
        Five for the original C kernel or four for explicit Rust arithmetic.

    Raises
    ------
    ValueError
        If a recorded backend is unknown or a Rust receipt lacks captured preparation identity.
    """
    if "kernel_backend" not in data:
        return RECORD_COUNT
    inputs = data.get("inputs")
    if (
        data["kernel_backend"] != "rust"
        or not isinstance(inputs, dict)
        or "rust_preparation.json" not in inputs
    ):
        message = "AMP original arithmetic backend or Rust preparation identity is invalid"
        raise ValueError(message)
    return RECORD_COUNT - 1


def verify_precompile_dependencies(directory: Path, data: dict[str, Any]) -> dict[str, str]:
    """Require original preprocessing records and current source bytes to match original snapshots.

    Parameters
    ----------
    directory
        Original admitted or byte-preserving relocated firmware image directory.
    data
        Original preparation receipt, never reconstructed from a compiled output.

    Returns
    -------
    dict of str to str
        Original compiler dependency identities after live and captured-byte reconciliation.

    Raises
    ------
    ValueError
        If actual preprocessing records, source/header bytes or original snapshots changed.
    """
    records = tuple(
        directory / "precompile" / f"input_{index}.d"
        for index in range(image_dependency_record_count(data))
    )
    hashes = {str(record.relative_to(directory)): sha256_of_file(record) for record in records}
    if data.get("dependency_records") != hashes:
        message = "AMP original firmware preprocessing records changed"
        raise ValueError(message)
    original = data.get("compiler_dependencies")
    validate_image_dependency_snapshot(directory, original)
    actual = image_dependency_hashes(records, directory)
    if original != actual:
        message = "AMP original firmware preprocessing dependencies changed"
        raise ValueError(message)
    return actual
