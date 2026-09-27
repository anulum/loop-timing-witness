# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native and host load source snapshots

"""Freeze actual build inputs and the optional host workload implementation."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

HOST_LOAD_SOURCES = (
    "linux_load.py",
    "linux_load_config.py",
    "linux_load_worker.py",
    "linux_load_channels.py",
    "linux_load_readiness.py",
    "linux_load_process.py",
    "manifest_io.py",
)


def snapshot_native_sources(root: Path, output: Path, *, host_load: bool = False) -> list[Path]:
    """Copy actual native, RTL and selected host implementation bytes for a new run.

    Parameters
    ----------
    root
        Actual repository root containing the production Makefile and source trees.
    output
        Owner's newly created run directory retaining the source snapshot.
    host_load
        Whether the run includes an actual owned workload and needs its sources.

    Returns
    -------
    list of Path
        Copied source paths within the run, ready for digest-bound provenance.

    Raises
    ------
    OSError
        If an actual source or snapshot destination cannot be accessed.
    """
    originals = [
        root / "Makefile",
        *(root / "rtl").glob("*.sv"),
        *(root / "runtime").rglob("*.cpp"),
        *(root / "runtime").rglob("*.h"),
        *(root / "controllers/c").glob("*.c"),
        *(root / "controllers/c").glob("*.h"),
    ]
    if host_load:
        originals.extend(root / "tools" / name for name in HOST_LOAD_SOURCES)
    snapshots = []
    for original in sorted(originals):
        destination = output / "source" / original.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        snapshots.append(destination)
    return snapshots
