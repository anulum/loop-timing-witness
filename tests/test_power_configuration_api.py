# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real PAC1934 typed configuration boundary

"""Refuse malformed public acquisition structures before actual Linux device selection.

Physical rail reads require a real PAC1934 instance. This corpus exercises the nearest
available public boundary: invalid rail/shunt structures refuse before constructing a device.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import REPOSITORY_ROOT


@pytest.fixture(scope="module")
def power_api_program() -> Path:
    """Build the actual PAC1934 constructor with strict warnings and compiler counters.

    Returns
    -------
    Path
        Public API corpus linked to the production IIO implementation.
    """
    directory = Path(
        os.environ.get("WITNESS_POWER_BUILD_ROOT", str(REPOSITORY_ROOT / "build/power_api"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "power_configuration_api_test"
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        "--coverage",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wconversion",
        "-Wshadow",
        *[
            str(REPOSITORY_ROOT / name)
            for name in (
                "tests/native/power_configuration_api_test.cpp",
                "runtime/linux/power_configuration.cpp",
                "runtime/linux/pac1934_device.cpp",
            )
        ],
        "-o",
        str(program),
    ]
    result = subprocess.run(
        command, cwd=directory, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return program


@pytest.mark.parametrize(
    "scenario",
    [
        "device",
        "device_prefix",
        "device_suffix",
        "kernel",
        "kernel_empty",
        "kernel_long",
        "period_low",
        "period_high",
        "span_zero",
        "span_high",
        "worker",
        "rate",
        "rail",
        "channel_zero",
        "channel_high",
        "shunt_zero",
        "shunt_high",
        "label",
        "label_empty",
        "label_long",
        "duplicate",
        "rate_8",
        "rate_64",
        "rate_256",
        "rate_1024",
    ],
)
def test_typed_power_refusal(power_api_program: Path, tmp_path: Path, scenario: str) -> None:
    """Check typed configuration and real missing-device refusal through the constructor.

    Parameters
    ----------
    power_api_program
        Strict native executable using actual Linux IIO selection.
    tmp_path
        Valid configuration allocation without fabricated sysfs nodes.
    scenario
        Invalid typed field or supported sample rate followed by actual absent-IIO refusal.
    """
    device = "iio:device4294967295"
    assert not (Path("/sys/bus/iio/devices") / device).exists()
    config = tmp_path / "power.conf"
    config.write_text(
        f"pac1934-iio-mchp-v1 {device} {os.uname().release} 60000000 50000000 "
        f"{min(os.sched_getaffinity(0))} 1024\n"
        "VDD 1 10000 rail1\nVDD25 2 10000 rail2\nVDDA25 3 10000 rail3\nVDDA 4 10000 rail4\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(power_api_program), scenario, str(config)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified {scenario}\n"
    assert result.stderr == ""
