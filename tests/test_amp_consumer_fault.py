# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual invalid consumer startup publication

"""Require the unchanged target to refuse a real logger's invalid startup release."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from amp_consumer_fault_plugin import ConsumerFaultPlugin, consumer_fault_plugin
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["consumer_fault_plugin"]


def test_actual_firmware_refuses_invalid_consumer_state(
    tmp_path: Path, consumer_fault_plugin: ConsumerFaultPlugin
) -> None:
    """Violate one real consumer transition and observe the exact target refusal.

    Parameters
    ----------
    tmp_path
        Exclusive original target image, simulator command and raw failed outputs.
    consumer_fault_plugin
        Diagnostic plugin retaining the original SDK and production RTL objects while its
        logger publishes one deliberately invalid consumer-owned transition.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]),
            consumer_fault_plugin.path,
            100,
            10000000,
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    if consumer_fault_plugin.fault == "invalid-ready":
        assert "AMP firmware refused or telemetry overflowed: cause=264 value=99" in result.stderr
    elif consumer_fault_plugin.fault == "corrupt-ready-mailbox":
        assert "AMP firmware refused or telemetry overflowed: cause=263 value=0" in result.stderr
    else:
        assert "ACTUAL_INVALID_COMPLETE cause=264 value=99" in result.stderr
    if consumer_fault_plugin.fault == "invalid-complete":
        assert 'WITNESS_AMP_COMPLETION {"samples":10,"events":40' in result.stdout
        assert (output / "events.bin").stat().st_size == 640
        assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    else:
        assert "WITNESS_AMP_COMPLETION" not in result.stdout
        assert not (output / "events.bin").read_bytes()
        assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
