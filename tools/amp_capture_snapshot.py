# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — verified AMP input snapshot custody

"""Copy only admitted image inputs and refuse changed bytes before or after target execution."""

from __future__ import annotations

import shutil
from pathlib import Path

from manifest_io import sha256_of_file


def snapshot_image(image: Path, output: Path, expected: dict[str, str]) -> None:
    """Freeze exact admitted image bytes into a new capture directory.

    Parameters
    ----------
    image
        Actual admitted original prepared image.
    output
        New exclusive image snapshot directory.
    expected
        Original relative artifact names and admitted SHA-256 values.

    Raises
    ------
    OSError
        If original input or exclusive output cannot be accessed.
    ValueError
        If a name escapes the image or original bytes changed after admission.
    """
    for name in expected:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            message = "AMP snapshot requires admitted relative input paths"
            raise ValueError(message)
    output.mkdir()
    for name, digest in expected.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image / name, destination)
        if sha256_of_file(destination) != digest:
            message = "AMP original image changed during capture snapshot"
            raise ValueError(message)


def verify_snapshot(directory: Path, expected: dict[str, str]) -> None:
    """Refuse post-start mutation of any captured original executable or source input.

    Parameters
    ----------
    directory
        Exact captured image snapshot.
    expected
        Exact admitted hashes used during initial copy.

    Raises
    ------
    OSError
        If an original snapshot input disappeared.
    ValueError
        If captured bytes changed while the target executed.
    """
    for name, digest in expected.items():
        if sha256_of_file(directory / name) != digest:
            message = "AMP captured executable inputs changed during execution"
            raise ValueError(message)
