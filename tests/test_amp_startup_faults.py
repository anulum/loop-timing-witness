# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual RV64 startup publication faults

"""Execute damaged original startup stores against the production mailbox consumer."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_target import (
    build_firmware,
    compile_command,
    link_command,
    spike_run,
    symbol_offset,
    target_platform,
)
from test_amp_logger import logger_image

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["logger_image"]


def _replace_main_instructions(image: Path, original: str, damaged: str) -> tuple[Path, int]:
    """Replace one original instruction sequence inside the target main function.

    Parameters
    ----------
    image
        Image directory with ``firmware.elf`` and ``platform.dtb``.
    original
        Hexadecimal instruction bytes that must occur exactly once in main.
    damaged
        Hexadecimal replacement of the same length.

    Returns
    -------
    tuple[Path, int]
        Changed firmware file and the file offset of the replaced bytes.
    """
    firmware = image / "firmware.elf"
    content = firmware.read_bytes()
    symbol = read_symbols(content)["witness_amp_main"]
    segments = admit_elf(content, target_platform(image)[1].memory.firmware)
    start = symbol_offset(segments, symbol.address)
    body = content[start : start + symbol.size]
    before, after = bytes.fromhex(original), bytes.fromhex(damaged)
    assert len(before) == len(after)
    assert body.count(before) == 1, "original compiler startup store sequence changed"
    offset = start + body.index(before)
    altered = bytearray(content)
    altered[offset : offset + len(before)] = after
    firmware.write_bytes(altered)
    return firmware, offset


@pytest.mark.parametrize("thermal", [0, 1])
@pytest.mark.parametrize(
    "case",
    [
        # GCC 15.2 sequences (riscv64-linux-gnu-gcc-15). The mailbox base is a2.
        # Keep the actual integral-max store `c.sw a0,104(a2)`, then publish that register
        # instead of zero: `sw zero,108(a2)` becomes `sw a0,108(a2)` or `sw a0,44(a2)`.
        (
            "run-reserved",
            "28d623260606",
            "28d62326a606",
            "AMP run contract reserved field changed",
        ),
        (
            "fresh-mailbox",
            "28d623260606",
            "28d62326a602",
            "AMP firmware did not initialize a fresh mailbox",
        ),
        # Publish a4, which still holds the checked logger status 2, instead of ARMED (1)
        # before START: `c.sw a1,4(a2)` becomes `c.sw a4,4(a2)`; the fence stays.
        (
            "arm-status",
            "4cc20f00f00f",
            "58c20f00f00f",
            "AMP firmware did not arm a fresh run",
        ),
    ],
)
def test_actual_startup_publication_fault(
    tmp_path: Path, thermal: int, case: tuple[str, str, str, str]
) -> None:
    """Refuse actual RV64 mailbox stores before any controller or fabric run starts.

    Parameters
    ----------
    tmp_path
        Exclusive original ELF copy, instruction mutation and raw simulator output.
    thermal
        Actual production mechanical or thermal RTL model.
    case
        Publication name, exact original GCC RV64 instruction sequence, same-length store
        fault and required public refusal. The sequence must occur once inside the main symbol;
        all other original instructions remain unchanged.
    """
    name, original, damaged, finding = case
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    firmware, offset = _replace_main_instructions(image, original, damaged)
    output = tmp_path / "execution"
    output.mkdir()
    (output / "target-mutation.json").write_text(
        json.dumps(
            {
                "fault": name,
                "file_offset": offset,
                "original_instructions": original,
                "damaged_instructions": damaged,
                "elf_sha256": sha256_of_file(firmware),
            }
        )
    )
    plugin = os.environ["WITNESS_SPIKE_THERMAL_PLUGIN" if thermal else "WITNESS_SPIKE_PLUGIN"]
    result = spike_run(image, Path(plugin), output)
    assert result.returncode != 0
    assert finding in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (output / "events.bin").read_bytes()
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


def test_actual_delayed_firmware_initialization(
    logger_image: tuple[Path, Path], tmp_path: Path
) -> None:
    """Wait for actual target initialization and complete both raw streams after a real CPU delay.

    Parameters
    ----------
    logger_image
        Actual original firmware objects, zero-fault IRQ wrapper and production RTL plugin.
    tmp_path
        Exclusive delayed target link, native commands and observed output.
    """
    original, plugin = logger_image
    image = tmp_path / "image"
    shutil.copytree(original, image)
    shutil.copy2(ROOT / "tests/native/amp_boot_delay.c", image / "boot_delay.c")
    commands = [
        compile_command("boot_delay"),
        link_command(
            ["objects/mailbox_fault.o", "objects/boot_delay.o"],
            ["witness_amp_trap", "witness_amp_main"],
        ),
    ]
    build_firmware(image, commands, "delay_build")
    output = tmp_path / "execution"
    result = spike_run(image, plugin, output)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"samples":10,"events":40,"misses":0,"overflow":0,"safe":false' in result.stdout
    assert (output / "events.bin").stat().st_size == 640
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
