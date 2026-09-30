# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual invalid fabric cycle observations

"""Require unchanged target refusal for invalid actual MMIO cycle observations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from amp_cycle_fault_plugin import CycleFaultPlugin, cycle_fault_plugin
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["cycle_fault_plugin"]


def test_actual_firmware_refuses_invalid_cycle_observation(
    tmp_path: Path, cycle_fault_plugin: CycleFaultPlugin
) -> None:
    """Corrupt one real cycle-register response and observe target cause ``0x101``.

    Parameters
    ----------
    tmp_path
        Exclusive original target image, simulator command and raw failed outputs.
    cycle_fault_plugin
        Diagnostic plugin retaining the original SDK and production RTL objects while
        corrupting one cycle-register response after the actual AXI transaction.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), cycle_fault_plugin.path, 100, 10000000),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    expected_value = 10 if cycle_fault_plugin.fault == "out-of-range" else 0
    assert result.returncode != 0
    assert (
        f"AMP firmware refused or telemetry overflowed: cause=257 value={expected_value}"
        in result.stderr
    )
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    expected_events = 1 if cycle_fault_plugin.fault == "out-of-range" else 5
    expected_tracking_lines = 1 if cycle_fault_plugin.fault == "out-of-range" else 2
    assert (output / "events.bin").stat().st_size == expected_events * 16
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == expected_tracking_lines
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
