# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP logger completion and captured stream agreement

"""Read actual compiler dependency records without omitting system or SDK headers."""

from __future__ import annotations

import shlex
from pathlib import Path

from .manifest_io import sha256_of_file


def dependency_hashes(records: tuple[Path, ...], directory: Path) -> dict[str, str]:
    """Hash the complete actual source/header closure recorded by native compilers.

    Parameters
    ----------
    records
        Nonempty complete selected compiler dependency records.
    directory
        Original compiler working directory for relative dependency names.

    Returns
    -------
    dict of str to str
        Resolved original source/system/SDK paths and SHA-256 identities.

    Raises
    ------
    OSError
        If an original record or dependency is unavailable.
    ValueError
        If a record lacks its target or complete nonempty dependency list.
    """
    if not records:
        message = "AMP build requires actual compiler dependency records"
        raise ValueError(message)
    result: dict[str, str] = {}
    for record in records:
        text = record.read_text(encoding="utf-8").replace("\\\n", "")
        target, separator, words = text.partition(":")
        if not target.strip() or not separator:
            message = "AMP original compiler dependency record is malformed: missing target"
            raise ValueError(message)
        names = shlex.split(words)
        if not names:
            message = "AMP original compiler dependency record is empty"
            raise ValueError(message)
        for name in names:
            path = Path(name.replace("$$", "$"))
            original = path if path.is_absolute() else directory / path
            resolved = original.resolve()
            result[str(resolved)] = sha256_of_file(resolved)
    return result
