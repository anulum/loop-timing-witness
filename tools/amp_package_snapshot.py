# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — portable original firmware verifier package snapshot

"""Retain the actual package used by original standalone firmware verification commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def snapshot_verifier_package(repository: Path, output: Path) -> None:
    """Copy package sources and resources beside captured original verifier entry points.

    Parameters
    ----------
    repository
        Original source checkout containing the actual package implementations.
    output
        New exclusive firmware preparation directory. Its original input record
        hashes every copied file before firmware compilation.

    Raises
    ------
    OSError
        If original package files or exclusive destinations cannot be accessed.
    """
    package = repository / "src/loop_timing_witness"
    # stat fails before copying when the original source package is absent.
    package.stat()
    for source in package.rglob("*"):
        if source.is_file() and (source.suffix in (".py", ".json") or source.name == "py.typed"):
            destination = output / "source/tools/loop_timing_witness" / source.relative_to(package)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(source.read_bytes())
