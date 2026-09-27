# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — acquisition journal CLI boundaries

"""Keep physical acquisition options unavailable to simulation and incomplete runs."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run
from test_native_uio_run import native_uio

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run", "native_uio"]


@pytest.mark.parametrize("option", ["--power-config", "--power-journal"])
def test_incomplete_power_options(native_uio: Path, tmp_path: Path, option: str) -> None:
    """Refuse a lone acquisition option before reading files or touching hardware.

    Parameters
    ----------
    native_uio
        Actual native UIO executable.
    tmp_path
        Exclusive output directory.
    option
        One member of the required acquisition option pair.
    """
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [
            str(native_uio),
            str(tmp_path / "absent.conf"),
            str(events),
            str(raw),
            "uio4294967295",
            "witness",
            "devicetree",
            "0",
            "0",
            option,
            str(tmp_path / "power"),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "must be supplied together" in result.stderr
    assert not events.exists()
    assert not raw.exists()


def test_simulation_refuses_physical_power(native_run: Path, tmp_path: Path) -> None:
    """Reject acquisition in each actual RTL model without inventing a power device.

    Parameters
    ----------
    native_run
        Production native controller linked to the actual RTL model.
    tmp_path
        Exclusive run directory.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw, journal = (tmp_path / name for name in ("events.bin", "raw.csv", "power.csv"))
    result = subprocess.run(
        [
            str(native_run),
            str(config),
            str(events),
            str(raw),
            "--metadata",
            str(tmp_path / "metadata.json"),
            "--power-config",
            str(tmp_path / "power.conf"),
            "--power-journal",
            str(journal),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "physical UIO-only" in result.stderr
    assert not any(path.exists() for path in (events, raw, journal))


def test_power_requires_metadata(native_uio: Path, tmp_path: Path) -> None:
    """Refuse unbound physical acquisition before reading any device or configuration.

    Parameters
    ----------
    native_uio
        Actual native UIO controller entry.
    tmp_path
        Exclusive run allocation.
    """
    result = subprocess.run(
        [
            str(native_uio),
            "absent.conf",
            str(tmp_path / "events.bin"),
            str(tmp_path / "raw.csv"),
            "uio4294967295",
            "witness",
            "devicetree",
            "0",
            "0",
            "--power-config",
            "absent-power.conf",
            "--power-journal",
            str(tmp_path / "power.csv"),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "requires native metadata" in result.stderr
    assert not list(tmp_path.iterdir())
