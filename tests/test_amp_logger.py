# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual target mutations and native AMP logger ownership

"""Execute production IRQ service and actual target RAM corruption against the native logger."""

from __future__ import annotations

import csv
import json
import os
import shutil
import struct
import subprocess
from io import StringIO
from pathlib import Path

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from event_stream import decode_events
from test_amp_spike_command import REQUEST
from test_native_run_output import OUTPUT_LIMIT_COMMAND

from manifest_io import sha256_of_file

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


@pytest.fixture(scope="module", params=[False, True])
def logger_image(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, Path]:
    """Link an actual target mutation wrapper around the unchanged production IRQ handler.

    Parameters
    ----------
    request
        Actual mechanical or thermal production plugin selection.
    tmp_path_factory
        Exclusive original image, actual extra object and real compiler output.

    Returns
    -------
    tuple of Path and Path
        Owned target image and explicitly selected actual production RTL plugin.
    """
    image = tmp_path_factory.mktemp("amp-logger-target") / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    shutil.copy2(ROOT / "tests/native/amp_mailbox_fault.c", image / "mailbox_fault.c")
    compiler = os.environ["WITNESS_RV64_CC"]
    objects = ["objects/input_" + str(index) + ".o" for index in range(5)]
    commands = [
        [
            compiler,
            *FLAGS,
            "-Isource",
            "-MD",
            "-MF",
            "objects/mailbox_fault.o.d",
            "-c",
            "mailbox_fault.c",
            "-o",
            "objects/mailbox_fault.o",
        ],
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
            *objects,
            "objects/mailbox_fault.o",
            "-Wl,--wrap=witness_amp_trap",
            "-o",
            "firmware.elf",
        ],
    ]
    (image / "fault_build.argv.json").write_text(json.dumps(commands, indent=2), encoding="ascii")
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, cwd=image, capture_output=True, text=True, check=False)
        (image / f"fault_build_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    plugin = os.environ["WITNESS_SPIKE_THERMAL_PLUGIN" if request.param else "WITNESS_SPIKE_PLUGIN"]
    return image, Path(plugin)


@pytest.mark.parametrize(
    ("fault", "finding", "cycles"),
    [
        (0, "", 10),
        (0, "", 300),
        (1, "AMP firmware refused or telemetry overflowed: cause=256 value=0", 10),
        (2, "AMP ABI disappeared during the run", 10),
        (3, "AMP telemetry ABI mismatch", 10),
        (4, "unknown AMP firmware status", 10),
        (5, "AMP telemetry consumer ownership changed", 10),
        (6, "AMP shared ownership or reserved fields changed", 10),
        (7, "AMP shared ownership or reserved fields changed", 10),
        (8, "AMP producer advanced beyond telemetry capacity", 10),
        (9, "AMP telemetry contradicts the observed sample sequence", 10),
        (10, "AMP telemetry contradicts the observed sample sequence", 10),
        (11, "AMP shared ownership or reserved fields changed", 10),
        (12, "AMP sample count differs from consumed telemetry", 10),
        (13, "AMP shared ownership or reserved fields changed", 10),
        (14, "AMP telemetry contradicts the observed sample sequence", 10),
        (15, "AMP telemetry contradicts the observed sample sequence", 10),
        (16, "AMP telemetry contradicts the observed sample sequence", 10),
        (17, "AMP telemetry contradicts the observed sample sequence", 10),
        (18, "AMP telemetry contradicts the observed sample sequence", 10),
        (19, "AMP telemetry contradicts the observed sample sequence", 10),
        (20, "AMP trap state contradicts active firmware status", 10),
        (21, "AMP trap state contradicts active firmware status", 10),
        (22, "AMP completion precedes the actual fabric run finish", 10),
    ],
)
def test_actual_target_mailbox_admission(
    logger_image: tuple[Path, Path], tmp_path: Path, fault: int, finding: str, cycles: int
) -> None:
    """Refuse real post-IRQ corruption and actual full-ring production refusal before completion.

    Parameters
    ----------
    logger_image
        Genuine compiled test wrapper and actual production IRQ handler, plus the RTL plugin.
    tmp_path
        Exclusive target ELF mutation, simulator argv and actual raw outputs.
    fault
        Deliberate target corruption, or zero for the unmodified wrapper baseline.
    finding
        Exact public native refusal; the zero baseline must complete all real samples.
    cycles
        Actual target cycle count; 300 exercises producer/consumer reuse of all ring slots.
    """
    original, plugin = logger_image
    image = tmp_path / "image"
    shutil.copytree(original, image)
    firmware = image / "firmware.elf"
    data = firmware.read_bytes()
    symbols = read_symbols(data)
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    segments = admit_elf(data, platform.memory.firmware)
    altered = bytearray(data)
    for name, value in (("witness_amp_test_fault", fault), ("witness_amp_run", cycles)):
        symbol = symbols[name]
        segment = next(
            part
            for part in segments
            if part.address <= symbol.address < part.address + part.file_bytes
        )
        struct.pack_into("<I", altered, segment.offset + symbol.address - segment.address, value)
    firmware.write_bytes(altered)
    configuration = image / "configuration.txt"
    tokens = configuration.read_text().split()
    tokens[1] = str(cycles)
    configuration.write_text(" ".join(tokens) + "\n", encoding="ascii")
    output = tmp_path / "execution"
    output.mkdir()
    (output / "target-mutation.json").write_text(
        json.dumps({"fault": fault, "cycles": cycles, "elf_sha256": sha256_of_file(firmware)}),
        encoding="ascii",
    )
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]),
            plugin,
            100,
            max(10000000, cycles * int(tokens[2]) * 10 + 1000000),
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2), encoding="ascii")
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr, encoding="ascii")
    if finding:
        assert result.returncode != 0
        assert finding in result.stderr
        assert "WITNESS_AMP_COMPLETION" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            f'"samples":{cycles},"events":{cycles * 4},"misses":0,"overflow":0,"safe":false'
            in result.stdout
        )
        assert (output / "events.bin").stat().st_size == cycles * 4 * 16
        rows = list(csv.DictReader(StringIO((output / "tracking_raw.csv").read_text())))
        assert [int(row["cycle"]) for row in rows] == list(range(cycles))
        assert [int(row["irq_generation"]) for row in rows] == list(range(1, cycles + 1))
        contracts = json.loads((ROOT / "measurement-domain.json").read_bytes())["design_contracts"]
        events = decode_events((output / "events.bin").read_bytes(), contracts, "CONTROL", cycles)
        samples = [event for event in events if event.name == "SAMPLE_READ"]
        assert [event.cycle for event in samples] == list(range(cycles))
        assert [event.ticks for event in samples] == [int(row["sample_ticks"]) for row in rows]
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    ("maximum", "finding"),
    [
        (0, "cannot write tracking header"),
        (32, "cannot write tracking header"),
        (512, "cannot finish run output"),
    ],
)
def test_actual_amp_output_failure(
    logger_image: tuple[Path, Path], tmp_path: Path, maximum: int, finding: str
) -> None:
    """Withhold successful target completion after real kernel write or final-close failures.

    Parameters
    ----------
    logger_image
        Actual baseline target and selected mechanical or thermal production plugin.
    tmp_path
        Exclusive command log and failed raw outputs.
    maximum
        Real child-only regular-file capacity enforced by the kernel.
    finding
        Required native failure before successful completion publication.
    """
    image, plugin = logger_image
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
    argv = [*OUTPUT_LIMIT_COMMAND, f"--fsize={maximum}:{maximum}", "--", *argv]
    (output / "command.json").write_text(json.dumps(argv, indent=2), encoding="ascii")
    result = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    (output / "spike.log").write_text(result.stdout + result.stderr, encoding="ascii")
    assert result.returncode != 0
    assert finding in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert (output / "events.bin").stat().st_size <= maximum
    assert (output / "tracking_raw.csv").stat().st_size == maximum
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
