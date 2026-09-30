# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — captured original native plugin source closure

"""Preserve original plugin source/header bytes and verify their captured receipt binding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .amp_plugin_receipt import decode_plugin_receipt
from .manifest_io import canonical_json_bytes, load_json_object, sha256_of_file


def source_index(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Assign reproducible run-local names to every original compiler/source/header dependency.

    Parameters
    ----------
    data
        Complete schema-valid original plugin build receipt.

    Returns
    -------
    dict of str to dict of str to str
        Original absolute dependency names mapped to unique local path/hash pairs.
    """
    return {
        name: {"path": f"plugin_sources/{index:04d}/source", "sha256": digest}
        for index, (name, digest) in enumerate(sorted(data["dependencies"].items()))
    }


def snapshot_plugin(output: Path, content: bytes) -> None:
    """Snapshot every original source/header with exclusive creation and hash readback.

    Parameters
    ----------
    output
        Newly allocated exclusive capture directory.
    content
        Original admitted plugin receipt bytes.

    Raises
    ------
    OSError
        If original dependencies or exclusive destinations are unavailable.
    ValueError
        If copied original dependency bytes disagree with the admitted receipt.
    """
    data = decode_plugin_receipt(content)
    index = source_index(data)
    (output / "plugin_sources").mkdir()
    for name, item in index.items():
        target = output / item["path"]
        target.parent.mkdir()
        with target.open("xb") as stream:
            stream.write(Path(name).read_bytes())
        if sha256_of_file(target) != item["sha256"]:
            message = "AMP plugin source changed while snapshotting"
            raise ValueError(message)
    with (output / "plugin_build.json").open("xb") as stream:
        stream.write(content)
    with (output / "plugin_source_index.json").open("xb") as stream:
        stream.write(canonical_json_bytes(index))


def validate_plugin_snapshot(output: Path, plugin_digest: str, *, thermal: bool) -> None:
    """Reconcile the original receipt and exact captured source closure with the executed library.

    Parameters
    ----------
    output
        Original completed capture directory.
    plugin_digest
        Hash of the actual executed plugin library from the capture receipt.
    thermal
        Plant parameter observed through the actual running RTL register.

    Raises
    ------
    OSError
        If original captured receipt, index or source bytes are unavailable.
    ValueError
        If source closure, library or actual plant parameter contradicts captured identities.
    """
    data = decode_plugin_receipt((output / "plugin_build.json").read_bytes())
    index = load_json_object(output / "plugin_source_index.json")
    if (
        data["plugin_sha256"] != plugin_digest
        or bool(data["thermal"]) != thermal
        or index != source_index(data)
    ):
        message = "AMP plugin snapshot library, plant or source index disagrees"
        raise ValueError(message)
    root = output.resolve()
    for item in index.values():
        path = output / item["path"]
        if not path.resolve().is_relative_to(root) or sha256_of_file(path) != item["sha256"]:
            message = "AMP captured plugin source bytes or paths changed"
            raise ValueError(message)
