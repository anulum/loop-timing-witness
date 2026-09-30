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
import subprocess
from pathlib import Path

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_logger import FLAGS, logger_image
from test_amp_spike_command import REQUEST

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
__all__ = ["logger_image"]


@pytest.mark.parametrize("thermal", [0, 1])
@pytest.mark.parametrize(
    "case",
    [
        # Keep the actual integral-max store, then publish that register instead of zero.
        (
            "run-reserved",
            "bcd423a60406",
            "bcd423a6f406",
            "AMP run contract reserved field changed",
        ),
        (
            "fresh-mailbox",
            "bcd423a60406",
            "bcd423a6f402",
            "AMP firmware did not initialize a fresh mailbox",
        ),
        # Publish the actual IRQ source register (2) instead of ARMED (1), before START.
        (
            "arm-status",
            "d8c00f00f00f",
            "d0c00f00f00f",
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
    firmware = image / "firmware.elf"
    content = firmware.read_bytes()
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    symbol = read_symbols(content)["witness_amp_main"]
    segment = next(
        part
        for part in admit_elf(content, platform.memory.firmware)
        if part.address <= symbol.address < part.address + part.file_bytes
    )
    start = segment.offset + symbol.address - segment.address
    body = content[start : start + symbol.size]
    before, after = bytes.fromhex(original), bytes.fromhex(damaged)
    assert len(before) == len(after)
    assert body.count(before) == 1, "original compiler startup store sequence changed"
    offset = start + body.index(before)
    altered = bytearray(content)
    altered[offset : offset + len(before)] = after
    firmware.write_bytes(altered)
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
    tools = SpikeTools(
        Path(os.environ["WITNESS_SPIKE"]),
        Path(os.environ["WITNESS_SPIKE_THERMAL_PLUGIN" if thermal else "WITNESS_SPIKE_PLUGIN"]),
        100,
        10000000,
    )
    argv = spike_command(
        tools, tree, platform, plic_path=REQUEST.plic.path, paths=SpikePaths(image, output)
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
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
    compiler = os.environ["WITNESS_RV64_CC"]
    commands = [
        [compiler, *FLAGS, "-c", "boot_delay.c", "-o", "objects/boot_delay.o"],
        [
            compiler,
            *FLAGS,
            "-nostdlib",
            "-nostartfiles",
            "-static",
            "-no-pie",
            "-Wl,--build-id=none",
            "-Wl,--defsym=__witness_ram_origin=2147483648",
            "-Wl,--defsym=__witness_ram_length=524288",
            "-Wl,--defsym=__witness_stack_size=16384",
            "-T",
            "source/runtime/bare_metal/firmware.ld",
            *["objects/input_" + str(index) + ".o" for index in range(5)],
            "objects/mailbox_fault.o",
            "objects/boot_delay.o",
            "-Wl,--wrap=witness_amp_trap",
            "-Wl,--wrap=witness_amp_main",
            "-o",
            "firmware.elf",
        ],
    ]
    (image / "delay_build.argv.json").write_text(json.dumps(commands, indent=2))
    for index, command in enumerate(commands):
        built = subprocess.run(command, cwd=image, capture_output=True, text=True, check=False)
        (image / f"delay_build_{index}.log").write_text(built.stdout + built.stderr)
        assert built.returncode == 0, built.stdout + built.stderr
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), plugin, 100, 10000000),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"samples":10,"events":40,"misses":0,"overflow":0,"safe":false' in result.stdout
    assert (output / "events.bin").stat().st_size == 640
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
