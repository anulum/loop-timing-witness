# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP target relinks, word changes and Spike runs

"""Relink, change and run copies of the actual AMP target image in Spike."""

from __future__ import annotations

import json
import os
import struct
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from amp_platform import AmpPlatform
    from device_tree_blob import DeviceTree

    from loop_timing_witness.amp_elf import LoadSegment

ROOT = Path(__file__).resolve().parents[1]
FLAGS = [
    "-std=gnu11",
    "-O2",
    "-ffreestanding",
    "-fno-builtin",
    "-fno-pie",
    "-march=rv64imac_zicsr_zifencei",
    "-mabi=lp64",
    "-mcmodel=medany",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wconversion",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
]
STATIC_LINK = ["-nostdlib", "-nostartfiles", "-static", "-no-pie", "-Wl,--build-id=none"]
_IMAGE_LINK = [
    *STATIC_LINK,
    "-Wl,--defsym=__witness_ram_origin=2147483648",
    "-Wl,--defsym=__witness_ram_length=524288",
    "-Wl,--defsym=__witness_stack_size=16384",
    "-T",
    "source/runtime/bare_metal/firmware.ld",
    *["objects/input_" + str(index) + ".o" for index in range(5)],
]


def compile_command(name: str, *options: str) -> list[str]:
    """Return the strict target compile command of one extra C file in an image.

    Parameters
    ----------
    name
        Stem of ``name.c`` in the image directory; the object is ``objects/name.o``.
    options
        Include and dependency options placed before ``-c``.

    Returns
    -------
    list[str]
        Argument vector run in the image directory.
    """
    compiler = os.environ["WITNESS_RV64_CC"]
    return [compiler, *FLAGS, *options, "-c", f"{name}.c", "-o", f"objects/{name}.o"]


def link_command(objects: Sequence[str], wrapped: Sequence[str]) -> list[str]:
    """Return the image link command with extra objects and wrapped target symbols.

    Parameters
    ----------
    objects
        Extra objects linked after the five original input objects.
    wrapped
        Original target symbols that the extra objects wrap.

    Returns
    -------
    list[str]
        Argument vector that writes ``firmware.elf`` in the image directory.
    """
    compiler = os.environ["WITNESS_RV64_CC"]
    wraps = ["-Wl,--wrap=" + name for name in wrapped]
    return [compiler, *FLAGS, *_IMAGE_LINK, *objects, *wraps, "-o", "firmware.elf"]


def build_firmware(image: Path, commands: list[list[str]], receipt: str) -> None:
    """Run target build commands in an image and keep their argv and logs.

    Parameters
    ----------
    image
        Image directory the commands run in.
    commands
        Compile and link argument vectors, in order.
    receipt
        Stem of ``receipt.argv.json`` and of each ``receipt_index.log``.
    """
    (image / f"{receipt}.argv.json").write_text(json.dumps(commands, indent=2), encoding="ascii")
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, cwd=image, capture_output=True, text=True, check=False)
        (image / f"{receipt}_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr


def target_platform(image: Path) -> tuple[DeviceTree, AmpPlatform]:
    """Decode the image device tree and admit its AMP platform.

    Parameters
    ----------
    image
        Image directory with ``platform.dtb``.

    Returns
    -------
    tuple[DeviceTree, AmpPlatform]
        Decoded tree and the platform admitted for the shared request.
    """
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    return tree, bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)


def symbol_offset(segments: Sequence[LoadSegment], address: int) -> int:
    """Return the file offset of a target address inside its file-backed load segment.

    Parameters
    ----------
    segments
        Admitted load segments of the ELF image.
    address
        Target address.

    Returns
    -------
    int
        Offset of the address in the ELF file.
    """
    segment = next(
        part for part in segments if part.address <= address < part.address + part.file_bytes
    )
    return segment.offset + address - segment.address


def write_symbol_words(image: Path, values: Mapping[str, int]) -> Path:
    """Write little-endian 32-bit words at named symbols of the image firmware.

    Parameters
    ----------
    image
        Image directory with ``firmware.elf`` and ``platform.dtb``.
    values
        Word to write at each symbol address.

    Returns
    -------
    Path
        Changed firmware file.
    """
    firmware = image / "firmware.elf"
    data = firmware.read_bytes()
    symbols = read_symbols(data)
    segments = admit_elf(data, target_platform(image)[1].memory.firmware)
    altered = bytearray(data)
    for name, value in values.items():
        struct.pack_into("<I", altered, symbol_offset(segments, symbols[name].address), value)
    firmware.write_bytes(altered)
    return firmware


def set_run_cycles(image: Path, cycles: int) -> list[str]:
    """Write the run cycle count into the image configuration.

    Parameters
    ----------
    image
        Image directory with ``configuration.txt``.
    cycles
        Target cycle count.

    Returns
    -------
    list[str]
        Configuration words after the change.
    """
    configuration = image / "configuration.txt"
    words = configuration.read_text().split()
    words[1] = str(cycles)
    configuration.write_text(" ".join(words) + "\n", encoding="ascii")
    return words


def spike_argv(image: Path, plugin: Path, output: Path, instructions: int = 10000000) -> list[str]:
    """Return the Spike command of the image with an RTL plugin.

    Parameters
    ----------
    image
        Image directory.
    plugin
        Spike plugin with the production RTL model.
    output
        Directory for the raw outputs; created when absent.
    instructions
        Instruction limit of the run.

    Returns
    -------
    list[str]
        Argument vector of the run.
    """
    tree, platform = target_platform(image)
    output.mkdir(exist_ok=True)
    return spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), plugin, 100, instructions),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )


def run_argv(
    argv: list[str], output: Path, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one Spike command and keep it and its log beside the raw outputs.

    Parameters
    ----------
    argv
        Argument vector.
    output
        Directory for ``command.json`` and ``spike.log``.
    environment
        Complete child environment, or ``None`` to inherit this process's one.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Finished Spike process.
    """
    (output / "command.json").write_text(json.dumps(argv, indent=2), encoding="ascii")
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=scaled(30),
        check=False,
    )
    (output / "spike.log").write_text(result.stdout + result.stderr)
    return result


def spike_run(
    image: Path,
    plugin: Path,
    output: Path,
    instructions: int = 10000000,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the image in Spike with an RTL plugin and keep the command and its log.

    Parameters
    ----------
    image
        Image directory.
    plugin
        Spike plugin with the production RTL model.
    output
        Directory for the raw outputs, ``command.json`` and ``spike.log``; created
        when absent.
    instructions
        Instruction limit of the run.
    environment
        Complete child environment, or ``None`` to inherit this process's one.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Finished Spike process.
    """
    return run_argv(spike_argv(image, plugin, output, instructions), output, environment)
