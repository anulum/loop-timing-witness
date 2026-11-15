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

from loop_timing_witness.host_profile import scaled

__all__ = ["amp_uio_program", "native_uio"]
# An absent UIO device, then its name, version, map index and physical address (run_uio).
UIO_DEVICE = ("uio4294967295", "witness", "devicetree", "0", "0")
MESSAGES = {
    "invalid_cycles": "invalid cycles, period or controller coefficients\n",
    "missing_iio": "native execution failed\n",
}


def _write_power_configuration(path: Path, device: str, cpu: int) -> None:
    """Write a four-rail PAC1934 configuration that names one IIO device.

    Parameters
    ----------
    path
        Configuration file.
    device
        IIO device name.
    cpu
        CPU of the power sampler.
    """
    tokens = [
        "pac1934-iio-mchp-v1",
        device,
        os.uname().release,
        "60000000",
        "50000000",
        str(cpu),
        "1024",
    ]
    for channel, rail in enumerate(("VDD", "VDD25", "VDDA25", "VDDA"), 1):
        tokens.extend([rail, str(channel), "10000", f"rail{channel}"])
    path.write_text(" ".join(tokens), encoding="utf-8")


def _entry_arguments(
    placement: str, program: Path, run: Path, directory: Path, cpu: int
) -> list[str]:
    """Return the command line of the controller or the dedicated-firmware logger.

    Parameters
    ----------
    placement
        ``uio`` controller or ``amp`` logger.
    program
        The placement's production command.
    run
        Run configuration.
    directory
        Exclusive allocation for the outputs, the logger's resources and the
        power configuration ``power.conf``.
    cpu
        CPU of the controller or logger.

    Returns
    -------
    list[str]
        Command, positional arguments and the shared metadata, CPU and power options.
    """
    events, trace = directory / "events.bin", directory / "trace.csv"
    if placement == "amp":
        resources = directory / "resources.conf"
        resources.write_text(RESOURCE, encoding="utf-8")
        arguments = [str(program), str(run), str(resources), str(events), str(trace)]
    else:
        arguments = [str(program), str(run), str(events), str(trace), *UIO_DEVICE]
    return [
        *arguments,
        "--metadata",
        str(directory / "metadata.json"),
        "--cpu",
        str(cpu),
        "--power-config",
        str(directory / "power.conf"),
        "--power-journal",
        str(directory / "power.csv"),
    ]


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
    _write_power_configuration(power, device, cpus[1])
    events, trace, metadata, journal = (
        tmp_path / name for name in ("events.bin", "trace.csv", "metadata.json", "power.csv")
    )
    programs = {"amp": amp_uio_program, "uio": native_uio}
    arguments = _entry_arguments(placement, programs[placement], run, tmp_path, cpus[0])
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, timeout=scaled(10)
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == MESSAGES[cause]
    assert not any(path.exists() for path in (events, trace, metadata, journal))
