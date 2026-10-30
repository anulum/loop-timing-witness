# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — distinct runtime and worker installation roles

"""Refuse runtime aliases of genuine worker files through the public installation API."""

from __future__ import annotations

import hashlib
import platform
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from loop_timing_witness.neural_checker_installation import (
    CheckerInstalledFile,
    NeuralCheckerInstallation,
)
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError


@pytest.mark.parametrize("kind", ["name", "path", "both"])
def test_runtime_inventory_cannot_alias_a_real_worker(tmp_path: Path, kind: str) -> None:
    """Keep logical and physical worker roles distinct from actual runtime bindings.

    Parameters
    ----------
    tmp_path
        Owned copy used to isolate a logical-name collision from a physical alias.
    kind
        Logical name, physical path or simultaneous worker/runtime alias.
    """
    tracer = shutil.which("strace")
    assert tracer is not None
    files = []
    for name, path in (
        ("interpreter/python", Path(sys.executable).resolve()),
        ("tracer/strace", Path(tracer).resolve()),
    ):
        raw = path.read_bytes()
        files.append(CheckerInstalledFile(name, path, hashlib.sha256(raw).hexdigest(), len(raw)))
    installation = NeuralCheckerInstallation(
        files[0],
        files[1],
        tuple(files),
        (Path(__file__).resolve().parents[1] / "src",),
        platform.platform(),
        platform.release(),
    )
    installation.verify()
    worker = installation.worker_files()[0]
    if kind == "name":
        copy = tmp_path / "worker.py"
        copy.write_bytes(worker.path.read_bytes())
        alias = replace(worker, path=copy)
    elif kind == "path":
        alias = replace(worker, name="observed/runtime/worker-alias")
    else:
        alias = worker
    selected = replace(installation, files=(*installation.files, alias))
    with pytest.raises(NeuralCaptureRefusalError, match="worker/runtime roles contain an alias"):
        selected.verify()
