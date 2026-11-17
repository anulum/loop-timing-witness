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
from loop_timing_witness.host_profile import scaled

POWER_COVERAGE_DIRECTORY = "WITNESS_POWER_COVERAGE_DIRECTORY"


@pytest.fixture(scope="module")
def power_api_program() -> Path:
    """Build the actual PAC1934 constructor with strict warnings.

    When ``WITNESS_POWER_COVERAGE_DIRECTORY`` names a directory, the corpus is built there
    unoptimised with GCC line and branch counters for the host C++ runtime coverage gate.
    Otherwise the ordinary optimised build is used.

    Returns
    -------
    Path
        Public API corpus linked to the production IIO implementation.
    """
    coverage = os.environ.get(POWER_COVERAGE_DIRECTORY)
    if coverage:
        directory = Path(coverage)
        flags = ["-O0", "--coverage", "-fprofile-abs-path"]
    else:
        directory = REPOSITORY_ROOT / "build/power_api"
        flags = ["-O2"]
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "power_configuration_api_test"
    command = [
        "g++",
        "-std=c++17",
        *flags,
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
        command, cwd=directory, capture_output=True, text=True, check=False, timeout=scaled(30)
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
        timeout=scaled(5),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified {scenario}\n"
    assert result.stderr == ""


RAILS = "VDD 1 10000 rail1\nVDD25 2 10000 rail2\nVDDA25 3 10000 rail3\nVDDA 4 10000 rail4\n"


def _power_file(device: str, *, values: str = "60000000 50000000", rails: str | None = None) -> str:
    """Return a power configuration's text with a valid identity and chosen later fields.

    Parameters
    ----------
    device
        IIO device identity, absent from sysfs.
    values
        Period and maximum read time fields.
    rails
        Rail lines, or the four valid rails when omitted.

    Returns
    -------
    str
        Configuration text for the file reader.
    """
    if rails is None:
        rails = RAILS
    cpu = min(os.sched_getaffinity(0))
    return f"pac1934-iio-mchp-v1 {device} {os.uname().release} {values} {cpu} 1024\n{rails}"


IDENTITY = "invalid power ABI, IIO identity or kernel release"
RANGE = "power configuration integer outside range"


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("empty", IDENTITY),
        ("abi", IDENTITY),
        ("truncated", "incomplete power configuration"),
        ("word", RANGE),
        ("suffix", RANGE),
        ("low", RANGE),
        ("high", RANGE),
        ("rail_missing", "power rails must be VDD VDD25 VDDA25 VDDA in order"),
        ("label_missing", "invalid power label or duplicate channel"),
        ("extra", "extra or unreadable power configuration"),
    ],
)
def test_power_file_refusal(
    power_api_program: Path, tmp_path: Path, case: str, message: str
) -> None:
    """Refuse a malformed configuration file before any device selection.

    Parameters
    ----------
    power_api_program
        Strict native executable using the production file reader.
    tmp_path
        Configuration file allocation.
    case
        Malformation: missing or wrong fields, an out-of-range or non-numeric number, missing
        rail fields or trailing text.
    message
        Authored refusal the reader must raise.
    """
    device = "iio:device4294967295"
    texts = {
        "empty": "",
        "abi": _power_file(device).replace("mchp-v1", "mchp-v0", 1),
        "truncated": f"pac1934-iio-mchp-v1 {device} {os.uname().release}\n",
        "word": _power_file(device, values="sixty 50000000"),
        "suffix": _power_file(device, values="60000000x 50000000"),
        "low": _power_file(device, values="49999999 1"),
        "high": _power_file(device, values="60000000001 1"),
        "rail_missing": _power_file(device, rails=""),
        "label_missing": _power_file(device, rails=RAILS.rstrip().rsplit(" ", 1)[0] + "\n"),
        "extra": _power_file(device) + "extra\n",
    }
    config = tmp_path / "power.conf"
    config.write_text(texts[case], encoding="utf-8")
    result = subprocess.run(
        [str(power_api_program), "file", str(config), message],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(5),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "verified file\n"
    assert result.stderr == ""
