# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — UIO entry point refusal against actual Linux sysfs

"""Build the UIO entry point and verify refusal without inventing a device."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import REPOSITORY_ROOT


@pytest.fixture(scope="module")
def uio_transport() -> Path:
    """Compile the actual Linux transport with strict conversion and shadow checks.

    Returns
    -------
    Path
        Production UIO executable.
    """
    result = subprocess.run(
        ["make", "uio-transport"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return REPOSITORY_ROOT / "build/uio_transport"


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["uio0"],
        ["../uio0", "witness", "devicetree", "0", "0"],
        ["uio", "witness", "devicetree", "0", "0"],
        ["uio0", "", "devicetree", "0", "0"],
        ["uio0", "witness", "", "0", "0"],
        ["uio0", "witness", "devicetree", "-1", "0"],
        ["uio0", "witness", "devicetree", "4294967296", "0"],
        ["uio0", "witness", "devicetree", "0", "18446744073709551616"],
        ["uio0", "witness", "devicetree", "0", "-1"],
    ],
)
def test_invalid_uio_request(uio_transport: Path, arguments: list[str]) -> None:
    """Refuse malformed public identity before hardware selection or access.

    Parameters
    ----------
    uio_transport
        Actual compiled Linux entry point.
    arguments
        Invalid command line.
    """
    result = subprocess.run(
        [str(uio_transport), *arguments],
        input="R 124\n",
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr


def test_missing_real_uio_device(uio_transport: Path) -> None:
    """Refuse unavailable sysfs rather than substituting file-backed MMIO.

    Parameters
    ----------
    uio_transport
        Production UIO executable.
    """
    device = "uio4294967295"
    assert not (Path("/sys/class/uio") / device).exists()
    result = subprocess.run(
        [str(uio_transport), device, "loop-timing-witness", "devicetree", "0", "0"],
        input="R 124\n",
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "cannot read sysfs attribute" in result.stderr
