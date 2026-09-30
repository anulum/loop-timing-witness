# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original Rust source dependency reconciliation

"""Admit genuine Rust multi-rule dependency files without treating phony rules as sources."""

from __future__ import annotations

import shlex
from pathlib import Path

from .manifest_io import sha256_of_file


def _record_sources(text: str) -> set[str]:
    """Parse complete original multi-rule compiler evidence into its source dependency set.

    Parameters
    ----------
    text
        Actual dependency record with Make continuations already joined.

    Returns
    -------
    set of str
        Nonempty original source closure reconciled with compiler phony rules.

    Raises
    ------
    ValueError
        If a rule, output target or source/phony closure is malformed.
    """
    sources = set()
    phony = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        target, separator, words = line.partition(":")
        if not separator or not target.strip() or line.lstrip().startswith("#"):
            message = "Rust dependency rule is malformed or uses ambient environment"
            raise ValueError(message)
        targets = shlex.split(target)
        if len(targets) != 1:
            message = "Rust dependency rule requires one original output or phony target"
            raise ValueError(message)
        names = shlex.split(words)
        if names:
            sources.update(names)
        else:
            phony.add(targets[0])
    if not sources or not phony.issubset(sources):
        message = "Rust dependency source closure is empty or its phony rules disagree"
        raise ValueError(message)
    return sources


def rust_dependency_hashes(records: tuple[Path, ...], directory: Path) -> dict[str, str]:
    """Hash every original Rust source in actual metadata or library compiler dependency records.

    Parameters
    ----------
    records
        Nonempty genuine rustc dependency records, including output and phony source rules.
    directory
        Exclusive image root containing the captured source tree.

    Returns
    -------
    dict of str to str
        Image-relative source paths and current original byte hashes, independent of output kind.

    Raises
    ------
    ValueError
        If records, rules or sources are empty, malformed, escaped or depend on ambient variables.
    OSError
        If original records or dependency bytes cannot be read.
    """
    if not records:
        message = "Rust compilation requires actual dependency records"
        raise ValueError(message)
    root = directory.resolve()
    result = {}
    for record in records:
        text = record.read_text(encoding="utf-8").replace("\\\n", " ")
        sources = _record_sources(text)
        for name in sources:
            path = directory / name
            if Path(name).is_absolute() or not path.resolve().is_relative_to(root / "source"):
                message = "Rust dependency source paths escape the original source snapshot"
                raise ValueError(message)
            result[name] = sha256_of_file(path)
    return result
