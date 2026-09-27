# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual absent PAC1934 device refusal

"""Exercise actual kernel/IIO identity checks without simulated sysfs nodes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration
from test_native_uio_run import native_uio

__all__ = ["native_uio"]


@pytest.mark.parametrize("kernel", ["actual", "mismatch"])
def test_actual_iio_refusal(native_uio: Path, tmp_path: Path, kernel: str) -> None:
    """Preserve outputs when the actual kernel or requested IIO node is unavailable.

    Parameters
    ----------
    native_uio
        Actual native controller executable.
    tmp_path
        Exclusive run paths.
    kernel
        Actual host kernel release or explicit mismatched release.
    """
    device = "iio:device4294967295"
    assert not (Path("/sys/bus/iio/devices") / device).exists()
    cpus = sorted(os.sched_getaffinity(0))
    controller, worker = cpus[0], cpus[-1]
    release = os.uname().release if kernel == "actual" else "nonexistent-kernel"
    power = tmp_path / "power.conf"
    power.write_text(
        f"pac1934-iio-mchp-v1 {device} {release} 60000000 50000000 {worker} 1024\n"
        "VDD 1 10000 rail1\nVDD25 2 10000 rail2\nVDDA25 3 10000 rail3\nVDDA 4 10000 rail4\n",
        encoding="utf-8",
    )
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    outputs = [tmp_path / name for name in ("events.bin", "raw.csv", "power.csv")]
    result = subprocess.run(
        [
            str(native_uio),
            str(config),
            str(outputs[0]),
            str(outputs[1]),
            "uio4294967295",
            "witness",
            "devicetree",
            "0",
            "0",
            "--cpu",
            str(controller),
            "--metadata",
            str(tmp_path / "metadata.json"),
            "--power-config",
            str(power),
            "--power-journal",
            str(outputs[2]),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    expected = (
        "separate controller"
        if controller == worker
        else "kernel release differs"
        if kernel == "mismatch"
        else "cannot make canonical path"
    )
    assert expected in result.stderr
    assert not any(path.exists() for path in outputs)
