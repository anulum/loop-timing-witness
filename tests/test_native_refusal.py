# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native caller refusal and unexpected filesystem failures

"""Exercise actual native command boundaries without inventing an IIO device."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_amp_uio_run import RESOURCE, amp_uio_program
from test_native_run import configuration
from test_native_uio_run import native_uio

__all__ = ["amp_uio_program", "native_uio"]


@pytest.mark.parametrize("placement", ["uio", "amp"])
@pytest.mark.parametrize("cause", ["invalid_cycles", "missing_iio"])
def test_authored_and_unexpected_native_refusals(
    native_uio: Path, amp_uio_program: Path, tmp_path: Path, placement: str, cause: str
) -> None:
    """Keep authored refusals and map real filesystem failures before output acquisition.

    Parameters
    ----------
    native_uio
        Production Linux controller command.
    amp_uio_program
        Production dedicated-firmware logger command.
    tmp_path
        Exclusive configuration and output allocation.
    placement
        Controller or IRQ-free logger entry point.
    cause
        Invalid authored configuration or an actual unavailable kernel device.
    """
    cpus = sorted(os.sched_getaffinity(0))
    assert len(cpus) >= 2
    device = "iio:device4294967295"
    assert not (Path("/sys/bus/iio/devices") / device).exists()
    run = tmp_path / "run.conf"
    cycles = 0 if cause == "invalid_cycles" else 32
    run.write_text(
        configuration("pid", "none").replace("pid 32", f"pid {cycles}"), encoding="utf-8"
    )
    power = tmp_path / "power.conf"
    tokens = [
        "pac1934-iio-mchp-v1",
        device,
        os.uname().release,
        "60000000",
        "50000000",
        str(cpus[1]),
        "1024",
    ]
    for channel, rail in enumerate(("VDD", "VDD25", "VDDA25", "VDDA"), 1):
        tokens.extend([rail, str(channel), "10000", f"rail{channel}"])
    power.write_text(" ".join(tokens), encoding="utf-8")
    events, trace, metadata, journal = (
        tmp_path / name for name in ("events.bin", "trace.csv", "metadata.json", "power.csv")
    )
    if placement == "amp":
        resources = tmp_path / "resources.conf"
        resources.write_text(RESOURCE, encoding="utf-8")
        arguments = [str(amp_uio_program), str(run), str(resources), str(events), str(trace)]
    else:
        arguments = [
            str(native_uio),
            str(run),
            str(events),
            str(trace),
            "uio4294967295",
            "witness",
            "devicetree",
            "0",
            "0",
        ]
    arguments.extend(
        [
            "--metadata",
            str(metadata),
            "--cpu",
            str(cpus[0]),
            "--power-config",
            str(power),
            "--power-journal",
            str(journal),
        ]
    )
    result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 1
    assert result.stdout == ""
    messages = {
        "invalid_cycles": "invalid cycles, period or controller coefficients\n",
        "missing_iio": "native execution failed\n",
    }
    assert result.stderr == messages[cause]
    assert not any(path.exists() for path in (events, trace, metadata, journal))
