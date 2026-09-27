# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real metadata write failure and artifact custody

"""Refuse actual metadata output errors through the native controller entry point."""

from __future__ import annotations

import subprocess
from functools import partial
from typing import TYPE_CHECKING

from test_native_run import configuration, native_run
from test_native_run_output import limited_profile_environment, restrict_output_size

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


def test_metadata_write_failure(native_run: Path, tmp_path: Path) -> None:
    """Preserve completed single-cycle data and fail a real oversized metadata write.

    Parameters
    ----------
    native_run
        Actual production native controller against the selected RTL plant.
    tmp_path
        Exclusive input and result allocation.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none").replace("pid 32", "pid 1"), encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        preexec_fn=partial(restrict_output_size, 512),
        env=limited_profile_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "cannot write native metadata" in result.stderr
    assert result.stdout == ""
    assert events.stat().st_size == 4 * 16
    assert len(raw.read_text().splitlines()) == 2
    assert metadata.stat().st_size == 512


def test_existing_metadata_preserved(native_run: Path, tmp_path: Path) -> None:
    """Refuse metadata overwrite while retaining completed actual events and trace.

    Parameters
    ----------
    native_run
        Actual native run controller.
    tmp_path
        Exclusive run allocation with a preexisting metadata file.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    original = b"previous-completion-evidence\n"
    metadata.write_bytes(original)
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "cannot create exclusive native metadata" in result.stderr
    assert result.stdout == ""
    assert metadata.read_bytes() == original
    assert events.stat().st_size == 128 * 16
    assert len(raw.read_text().splitlines()) == 33
