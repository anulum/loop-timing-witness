# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native UIO controller public entry refusals

"""Verify actual native UIO entry behavior without a fabricated device."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled


@pytest.fixture(scope="module")
def native_uio() -> Path:
    """Build the same native run lifecycle with actual Linux UIO and strict C++.

    Returns
    -------
    Path
        Native in-process UIO controller executable.
    """
    result = subprocess.run(
        ["make", "run-uio"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return REPOSITORY_ROOT / "build/run_uio"


@pytest.mark.parametrize("fault", ["none", "overload"])
def test_unavailable_uio_run(native_uio: Path, tmp_path: Path, fault: str) -> None:
    """Refuse unavailable real sysfs or a simulation-only delay before output creation.

    Parameters
    ----------
    native_uio
        Production in-process UIO controller.
    tmp_path
        Managed configuration and output paths.
    fault
        Normal run or modeled overload that must be refused for physical execution.
    """
    device = "uio4294967295"
    assert not (Path("/sys/class/uio") / device).exists()
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", fault), encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    result = subprocess.run(
        [
            str(native_uio),
            str(config),
            str(events),
            str(tracking),
            device,
            "loop-timing-witness",
            "devicetree",
            "0",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(5),
    )
    assert result.returncode == 1
    expected = "cannot read sysfs attribute" if fault == "none" else "simulation-only"
    assert expected in result.stderr
    assert not events.exists()
    assert not tracking.exists()


def test_native_uio_usage(native_uio: Path) -> None:
    """Reject missing explicit hardware identity with a useful public usage line.

    Parameters
    ----------
    native_uio
        Actual compiled UIO controller.
    """
    result = subprocess.run([str(native_uio)], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "physical_address_decimal" in result.stderr


@pytest.mark.parametrize(
    ("fault", "option", "finding"),
    [
        ("drop", None, "a fault run needs --fault-uio, and only a fault run takes it"),
        ("none", "uio1 faults devicetree 0 4096", "only a fault run takes it"),
        ("drop", "uio1 faults", "fault-page UIO identity is incomplete"),
        ("drop", "uio1 faults devicetree 0 4096 extra", "unexpected argument"),
        (
            "drop",
            "uio1 faults devicetree 0 8192",
            "fault-page UIO is not the page after the run page",
        ),
        ("drop", "uio4294967294 faults devicetree 0 4096", "cannot read sysfs attribute"),
    ],
)
def test_fault_page_device_selection(
    native_uio: Path, tmp_path: Path, fault: str, option: str | None, finding: str
) -> None:
    """A fault run names the fault page's UIO device, the page after the run page, and only it does.

    Parameters
    ----------
    native_uio
        Production in-process UIO controller.
    tmp_path
        Managed configuration and output paths.
    fault
        Scheduled fault, or none.
    option
        ``--fault-uio`` value, or ``None`` to omit it.
    finding
        Required refusal before any output.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", fault), encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    arguments = [str(native_uio), str(config), str(events), str(tracking)]
    arguments += ["uio4294967295", "loop-timing-witness", "devicetree", "0", "0"]
    if option is not None:
        arguments += ["--fault-uio", option]
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, timeout=scaled(5)
    )
    assert result.returncode == 1
    assert finding in result.stderr
    assert not events.exists()
    assert not tracking.exists()
