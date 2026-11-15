# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual post-release startup admission matrix

"""Exercise every native startup short circuit after real logger release."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from amp_startup_admission_fault_plugin import startup_admission_fault_plugin
from amp_target import build_firmware, compile_command, link_command, spike_run

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["startup_admission_fault_plugin"]

MMIO_FAULTS = ("version", "sample-width", "period", "cycles", "startup-status", "enable-word")
MAILBOX_FAULTS = (
    "abi",
    "mailbox-status",
    "producer",
    "consumer",
    "overflow",
    "samples",
    "trap-cause",
    "trap-value",
    "logger-status",
)


@pytest.mark.parametrize("fault", [*MMIO_FAULTS, *MAILBOX_FAULTS, "submit-blocked"])
def test_actual_firmware_startup_admission_short_circuit(
    tmp_path: Path, startup_admission_fault_plugin: Path, fault: str
) -> None:
    """Change one real post-release observation and require the target response.

    Parameters
    ----------
    tmp_path
        Exclusive original target image, simulator command and raw output.
    startup_admission_fault_plugin
        Production RTL objects with one diagnostic observation boundary.
    fault
        Exact MMIO, mailbox or submission observation changed after READY.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    output = tmp_path / "execution"
    environment = {**os.environ, "WITNESS_STARTUP_ADMISSION_FAULT": fault}
    result = spike_run(image, startup_admission_fault_plugin, output, environment=environment)
    if fault == "submit-blocked":
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'WITNESS_AMP_COMPLETION {"samples":3,"events":24,"misses":10' in result.stdout
        assert '"safe":true' in result.stdout
        assert (output / "events.bin").stat().st_size == 384
        rows = (output / "tracking_raw.csv").read_text().splitlines()
        assert len(rows) == 4
        assert all(row.split(",")[9] == "0" for row in rows[1:])
    else:
        cause = 0x106 if fault in MMIO_FAULTS else 0x107
        assert result.returncode != 0
        assert f"ACTUAL_STARTUP_ADMISSION_REFUSAL cause={cause} value=0" in result.stderr
        assert not (output / "events.bin").read_bytes()
        assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_actual_zero_iteration_overload_skips_target_loop(
    tmp_path: Path, plugin_environment: str
) -> None:
    """Enter the real overload branch with zero iterations and complete both streams.

    Parameters
    ----------
    tmp_path
        Exclusive original image, changed run configuration and raw output.
    plugin_environment
        Mechanical or thermal production RTL plugin selection.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    configuration = image / "configuration.txt"
    tokens = configuration.read_text().split()
    tokens[19:24] = ["overload", "2", "1", "0", "0"]
    configuration.write_text(" ".join(tokens) + "\n")
    output = tmp_path / "execution"
    result = spike_run(image, Path(os.environ[plugin_environment]), output)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'WITNESS_AMP_COMPLETION {"samples":10,"events":41' in result.stdout
    rows = (output / "tracking_raw.csv").read_text().splitlines()
    assert len(rows) == 11
    assert rows[3].split(",")[12] == "0"
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


def test_actual_main_refuses_hart_changed_after_entry(
    tmp_path: Path, startup_admission_fault_plugin: Path
) -> None:
    """Reach the C hart-range guard after assembly admitted the original owner.

    Parameters
    ----------
    tmp_path
        Exclusive source-bound wrapper image and raw simulator output.
    startup_admission_fault_plugin
        Mechanical or thermal production RTL objects used by the real logger.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    shutil.copy2(ROOT / "tests/native/amp_invalid_hart_main.c", image / "invalid_hart_main.c")
    commands = [
        compile_command("invalid_hart_main", "-Isource"),
        link_command(["objects/invalid_hart_main.o"], ["witness_amp_main"]),
    ]
    build_firmware(image, commands, "invalid_hart_build")
    output = tmp_path / "execution"
    environment = {**os.environ, "WITNESS_STARTUP_ADMISSION_FAULT": "hart-range"}
    result = spike_run(image, startup_admission_fault_plugin, output, environment=environment)
    assert result.returncode != 0
    assert "AMP firmware refused or telemetry overflowed: cause=261 value=0" in result.stderr
    assert not (output / "events.bin").read_bytes()
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
