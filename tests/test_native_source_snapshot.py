# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native and worker source snapshot consumers

"""Require exact repository build and worker inputs through the public snapshot API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from native_source_snapshot import HOST_LOAD_SOURCES, snapshot_native_sources

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("host_load", [False, True])
def test_snapshot_preserves_actual_build_and_worker_bytes(
    tmp_path: Path, *, host_load: bool
) -> None:
    """Copy production inputs without substituting controller or worker sources.

    Parameters
    ----------
    tmp_path
        Exclusive source snapshot output.
    host_load
        Whether actual launcher and worker support inputs are required.
    """
    paths = snapshot_native_sources(REPOSITORY_ROOT, tmp_path, host_load=host_load)
    names = {path.relative_to(tmp_path / "source").as_posix() for path in paths}
    assert "Makefile" in names
    assert "runtime/isa/spike_plugin.mk" in names
    assert "runtime/linux/file_digest.cpp" in names
    assert "rtl/axi_control_witness.sv" in names
    assert "controllers/c/witness_controller.c" in names
    assert all(("tools/" + name in names) is host_load for name in HOST_LOAD_SOURCES)
    assert len(paths) == len(names)
    for path in paths:
        relative = path.relative_to(tmp_path / "source")
        assert path.read_bytes() == (REPOSITORY_ROOT / relative).read_bytes()
