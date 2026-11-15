# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual producer refusal after consumer starvation

"""Exercise the unchanged target producer against a suspended real telemetry consumer."""

from __future__ import annotations

import os
import shutil
import struct
from itertools import pairwise
from pathlib import Path

from amp_stall_plugin import stall_plugin
from amp_target import set_run_cycles, spike_run, write_symbol_words

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
    write_symbol_words(image, {"witness_amp_run": 300})
    set_run_cycles(image, 300)
    output = tmp_path / "execution"
    result = spike_run(image, stall_plugin, output, 100000000)
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
