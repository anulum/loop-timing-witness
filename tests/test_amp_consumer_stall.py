# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual producer refusal after consumer starvation

"""Exercise the unchanged target producer against a suspended real telemetry consumer."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from itertools import pairwise
from pathlib import Path

from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from amp_stall_plugin import stall_plugin
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["stall_plugin"]


def test_actual_producer_refuses_stalled_consumer(tmp_path: Path, stall_plugin: Path) -> None:
    """Fill all 256 real slots without overwriting retained samples or acknowledging completion.

    Parameters
    ----------
    tmp_path
        Exclusive real target image, simulator command and observed mailbox dump.
    stall_plugin
        Actual production mechanical or thermal RTL selection. The locally built
        diagnostic plugin suspends telemetry polling after its first real consumption,
        continues real event draining and observes firmware refusal without changing RAM.
        This scheduling fault variant must never be admitted as a scientific capture.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    firmware = image / "firmware.elf"
    content = firmware.read_bytes()
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    symbol = read_symbols(content)["witness_amp_run"]
    segment = next(
        part
        for part in admit_elf(content, platform.memory.firmware)
        if part.address <= symbol.address < part.address + part.file_bytes
    )
    altered = bytearray(content)
    struct.pack_into("<I", altered, segment.offset + symbol.address - segment.address, 300)
    firmware.write_bytes(altered)
    configuration = image / "configuration.txt"
    tokens = configuration.read_text().split()
    tokens[1] = "300"
    configuration.write_text(" ".join(tokens) + "\n")
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), stall_plugin, 100, 100000000),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert "AMP firmware refused or telemetry overflowed: cause=256 value=257" in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    observed = [
        line for line in result.stderr.splitlines() if line.startswith("ACTUAL_STALLED_MAILBOX ")
    ]
    assert len(observed) == 1
    words = list(map(int, observed[0].split()[1:]))
    assert len(words) == 16496 // 4
    mailbox = struct.pack("<" + str(len(words)) + "I", *words)
    (output / "actual_mailbox.bin").write_bytes(mailbox)
    assert words[:4] == [2, 3, 257, 1]
    assert struct.unpack_from("<QQ", mailbox, 16) == (256, 257)
    assert words[8:12] == [1, 257, 2, 0]
    retained = [
        struct.unpack_from("<QQQ I", mailbox, 112 + ((index & 255) * 64)) for index in range(1, 257)
    ]
    assert [record[3] for record in retained] == list(range(1, 257))
    assert [record[1] for record in retained] == list(range(2, 258))
    assert all(left[0] < right[0] for left, right in pairwise(retained))
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 2
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
