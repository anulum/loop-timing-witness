# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual dedicated-hart architectural trap and native refusal execution

"""Execute damaged original contracts in actual Spike to verify native defence in depth."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_run_input import read_amp_run
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from event_stream import decode_events
from test_amp_spike_command import REQUEST

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = struct.Struct("<II6Q")
RUN = struct.Struct("<4I11i")


def execute_damaged_contract(
    tmp_path: Path, case: tuple[str, int, int, int, int]
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Execute an owned damaged actual ELF with retained original simulator command and diagnostics.

    Parameters
    ----------
    tmp_path
        Exclusive whole original image copy and simulator output.
    case
        Native object, field index, damaged value and expected actual cause/value.

    Returns
    -------
    tuple of subprocess.CompletedProcess and Path
        Real simulator result and its retained exclusive output directory.
    """
    contract, field, value, cause, trap_value = case
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    firmware = image / "firmware.elf"
    original = firmware.read_bytes()
    symbol = read_symbols(original)[f"witness_amp_{contract}"]
    segment = next(
        segment
        for segment in admit_elf(original, platform.memory.firmware)
        if segment.address <= symbol.address < segment.address + segment.file_bytes
    )
    offset = segment.offset + symbol.address - segment.address
    layout = PLATFORM if contract == "platform" else RUN
    fields = list(layout.unpack_from(original, offset))
    fields[field] = value
    altered = bytearray(original)
    layout.pack_into(altered, offset, *fields)
    firmware.write_bytes(altered)
    output = tmp_path / "execution"
    output.mkdir()
    tools = SpikeTools(
        Path(os.environ["WITNESS_SPIKE"]),
        Path(os.environ["WITNESS_SPIKE_PLUGIN"]),
        100,
        10000000,
    )
    argv = spike_command(
        tools, tree, platform, plic_path=REQUEST.plic.path, paths=SpikePaths(image, output)
    )
    (output / "command.json").write_text(json.dumps(argv), encoding="ascii")
    (output / "damaged-contract.json").write_text(
        json.dumps(
            {
                "contract": contract,
                "field": field,
                "value": value,
                "firmware_sha256": sha256_of_file(firmware),
                "expected_cause": cause,
                "expected_trap_value": trap_value,
            }
        ),
        encoding="ascii",
    )
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr, encoding="ascii")
    return result, output


@pytest.mark.parametrize(
    "case",
    [
        ("platform", 2, 0, 0x104, 0),
        ("platform", 3, 0, 0x104, 1),
        ("platform", 4, 0, 0x104, 2),
        ("platform", 5, 0, 0x104, 3),
        ("platform", 6, 0, 0x104, 4),
        ("platform", 3, 2, 0x104, 1),
        ("platform", 1, 0, 0x105, 0),
        ("platform", 1, 1024, 0x105, 0),
        ("run", 0, 0, 0x105, 0),
        ("run", 1, 0, 0x105, 0),
        ("run", 2, 2, 0x105, 0),
        ("run", 3, 10000001, 0x105, 0),
        ("run", 7, -1, 0x105, 0),
        ("run", 1, 32769, 0x106, 0),
        ("platform", 2, 0x50000000, 5, 0x5000007C),
        ("platform", 4, 0x50000000, 5, 0x50000000),
    ],
)
def test_actual_native_contract_refusal(
    tmp_path: Path, case: tuple[str, int, int, int, int]
) -> None:
    """Require actual target refusal and real load-access traps, without a fabricated completion.

    Parameters
    ----------
    tmp_path
        Owned original image copy and actual simulator output.
    case
        Original contract, native field index, damaged value and expected real cause/value.
    """
    result, output = execute_damaged_contract(tmp_path, case)
    cause, trap_value = case[3:]
    assert result.returncode != 0
    if cause == 0x106:
        assert "AMP running firmware contract differs from logger configuration" in result.stderr
        assert not (output / "events.bin").read_bytes()
    else:
        assert (
            f"AMP firmware refused or telemetry overflowed: cause={cause} value={trap_value}"
            in (result.stdout + result.stderr)
        )
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("hart", [0, 5])
def test_actual_invalid_hart_parks_before_mailbox(tmp_path: Path, hart: int) -> None:
    """Keep every simulated hart parked when the compiled owner ID names no running hart.

    Parameters
    ----------
    tmp_path
        Exclusive damaged image and actual simulator output.
    hart
        Invalid compiled owner below or above the supported application-hart range.
    """
    result, output = execute_damaged_contract(tmp_path, ("platform", 0, hart, 0, 0))
    assert result.returncode != 0
    assert "Witness ISA simulation time limit exceeded" in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (output / "events.bin").read_bytes()
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (0, 9),
        (1, 32769),
        (2, 1),
        (3, 1),
        (4, 0),
        (5, 1),
        (6, 1),
        (7, 1),
        (8, 0),
        (9, 1),
        (10, 0),
        (11, -1),
        (12, 1),
        (13, -1),
        (14, 1),
    ],
)
def test_actual_published_run_contract_refusal(tmp_path: Path, field: int, value: int) -> None:
    """Require every actual published run word to match the logger before START or control service.

    Parameters
    ----------
    tmp_path
        Exclusive real target image and original simulator output.
    field
        Actual native contract word retained in the firmware's mailbox mirror.
    value
        Otherwise valid native scalar contradicting the original logger configuration.
    """
    result, output = execute_damaged_contract(tmp_path, ("run", field, value, 0, 0))
    assert result.returncode != 0
    assert "AMP running firmware contract differs from logger configuration" in result.stderr
    assert not (output / "events.bin").read_bytes()
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 1
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


def test_actual_unserviced_irq_retains_raw_records(tmp_path: Path) -> None:
    """Retain actual drained safe-state events when a missing IRQ prevents completion.

    Parameters
    ----------
    tmp_path
        Owned real damaged interrupt contract and original simulator output.
    """
    result, output = execute_damaged_contract(tmp_path, ("platform", 1, 1, 0, 0))
    assert result.returncode != 0
    assert "Witness ISA simulation time limit exceeded" in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    records = (output / "events.bin").read_bytes()
    configuration = read_amp_run((tmp_path / "image/configuration.txt").read_bytes())
    contracts = json.loads((ROOT / "measurement-domain.json").read_bytes())["design_contracts"]
    events = decode_events(records, contracts, "CONTROL", configuration.cycles)
    assert sum(event.name == "SAMPLE_READY" for event in events) == configuration.cycles
    assert sum(event.name == "DEADLINE" for event in events) == configuration.cycles
    safe = [event for event in events if event.name == "SAFE_STATE"]
    assert len(safe) == 1
    assert safe[0].cycle == 2
    assert all(event.name in {"SAMPLE_READY", "DEADLINE", "SAFE_STATE"} for event in events)
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
