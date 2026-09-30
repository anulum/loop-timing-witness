# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual captured firmware declaration and executable reconciliation

"""Refuse contradictory original image metadata through the public analysis command."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_image_options import verification_arguments
from amp_image_receipt import recorded_request
from amp_platform import bind_platform
from capture_amp_simulation import main as capture_main
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def original_capture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Execute original target firmware once before independently copying its completed capture.

    Parameters
    ----------
    tmp_path_factory
        Exclusive module build and actual capture directories.

    Returns
    -------
    Path
        Source-bound output of a successful public capture against actual Spike and production RTL.
    """
    directory = tmp_path_factory.mktemp("original-image-contract")
    image = directory / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    (image / "image.json").unlink()
    selection = verification_arguments(REQUEST)
    selection[selection.index("platform.dtb")] = str(image / "platform.dtb")
    selection[selection.index("configuration.txt")] = str(image / "configuration.txt")
    output = directory / "capture"
    assert (
        capture_main(
            [
                *selection,
                "--image",
                str(image),
                "--output",
                str(output),
                "--spike",
                os.environ["WITNESS_SPIKE"],
                "--plugin",
                os.environ["WITNESS_SPIKE_PLUGIN"],
                "--rtc-nanoseconds",
                "100",
                "--time-limit",
                "100000000",
                "--timeout",
                "60",
            ]
        )
        == 0
    )
    return output


def retain_revised_outer_hashes(directory: Path) -> None:
    """Recompute every changed outer hash while preserving original compiler and source identities.

    Parameters
    ----------
    directory
        Owned copy of an actual completed capture after one negative-test mutation.
    """
    capture_path = directory / "capture.json"
    capture = json.loads(capture_path.read_bytes())
    for name in capture["files"]:
        capture["files"][name] = sha256_of_file(directory / name)
    capture_path.write_text(json.dumps(capture), encoding="ascii")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["amp_capture"]["sha256"] = sha256_of_file(capture_path)
    manifest["source"]["files"] = [
        {"path": name, "sha256": digest} for name, digest in capture["files"].items()
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="ascii")


def analyze_copy(directory: Path) -> subprocess.CompletedProcess[str]:
    """Run public analysis on a complete real capture copy with exclusive report output.

    Parameters
    ----------
    directory
        Owned actual capture whose inner metadata may have been deliberately corrupted.

    Returns
    -------
    subprocess.CompletedProcess of str
        Public process result and retained diagnostics.
    """
    return subprocess.run(
        [
            sys.executable,
            "tools/analyze_run.py",
            str(directory / "manifest.json"),
            "--output-dir",
            str(directory.parent / "reanalysis"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("preparation", "schema", "unknown"),
        ("preparation", "isa", False),
        ("preparation", "isa", 1),
        ("preparation", "compiler", "/different/compiler"),
        ("preparation", "compiler_sha256", "0" * 64),
        ("image", "inputs", {}),
        ("image", "schema", "unknown"),
        ("image", "simulation_only", False),
        ("image", "physical_verified", True),
        ("image", "exit_mode", "parked"),
        ("image", "platform", {}),
        ("image", "run", {}),
        ("image", "stack_bytes", 8192),
        ("image", "segments", []),
    ],
)
def test_public_original_image_declarations(
    original_capture: Path, tmp_path: Path, section: str, field: str, value: object
) -> None:
    """Refuse every contradictory declaration despite complete recomputation of outer hashes.

    Parameters
    ----------
    original_capture
        Original real completed firmware and production RTL execution.
    tmp_path
        Exclusive owned mutation and process output directory.
    section
        Original preparation or verified image metadata.
    field
        Duplicated resource, source or mode declaration to contradict.
    value
        Explicit invalid declaration retained in the negative-test artifact.
    """
    directory = tmp_path / "capture"
    shutil.copytree(original_capture, directory)
    path = directory / "image" / f"{section}.json"
    data = json.loads(path.read_bytes())
    data[field] = value
    path.write_text(json.dumps(data), encoding="ascii")
    image_path = directory / "image/image.json"
    image = json.loads(image_path.read_bytes())
    image["preparation_sha256"] = sha256_of_file(directory / "image/preparation.json")
    image_path.write_text(json.dumps(image), encoding="ascii")
    retain_revised_outer_hashes(directory)
    result = analyze_copy(directory)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AMP original image" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "reanalysis").exists()


@pytest.mark.parametrize(
    "fault",
    ["missing", "short", "type", "relative-python", "script", "option", "dtb", "integer"],
)
def test_public_original_verification_vector(
    original_capture: Path, tmp_path: Path, fault: str
) -> None:
    """Refuse original verification selection corruption without executing recorded commands.

    Parameters
    ----------
    original_capture
        Actual completed source-bound target execution.
    tmp_path
        Exclusive owned command-receipt mutation.
    fault
        Specific vector shape, input-path or integer selection contradiction.
    """
    directory = tmp_path / "capture"
    shutil.copytree(original_capture, directory)
    commands_path = directory / "image/build_commands.json"
    commands = json.loads(commands_path.read_bytes())
    if fault == "missing":
        commands.pop("verify")
    elif fault == "short":
        commands["verify"].pop()
    else:
        index, value = {
            "type": (0, None),
            "relative-python": (0, "python"),
            "script": (1, "other.py"),
            "option": (4, "--other"),
            "dtb": (5, "different.dtb"),
            "integer": (23, "02"),
        }[fault]
        commands["verify"][index] = value
    commands_path.write_text(json.dumps(commands), encoding="ascii")
    preparation_path = directory / "image/preparation.json"
    preparation = json.loads(preparation_path.read_bytes())
    preparation["inputs"]["build_commands.json"] = sha256_of_file(commands_path)
    preparation_path.write_text(json.dumps(preparation), encoding="ascii")
    image_path = directory / "image/image.json"
    image = json.loads(image_path.read_bytes())
    image["inputs"]["build_commands.json"] = sha256_of_file(commands_path)
    image["preparation_sha256"] = sha256_of_file(preparation_path)
    image_path.write_text(json.dumps(image), encoding="ascii")
    retain_revised_outer_hashes(directory)
    result = analyze_copy(directory)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AMP original image verification" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "reanalysis").exists()


def test_public_actual_firmware_contract_bytes(original_capture: Path, tmp_path: Path) -> None:
    """Refuse changed actual linked run constants after all declared firmware hashes are revised.

    Parameters
    ----------
    original_capture
        Original actual firmware and matching topology.
    tmp_path
        Owned entire original ELF copy; installed tools and source captures remain intact.
    """
    directory = tmp_path / "capture"
    shutil.copytree(original_capture, directory)
    image_directory = directory / "image"
    request = recorded_request(image_directory)
    platform = bind_platform(
        decode_device_tree((image_directory / "platform.dtb").read_bytes()),
        request.memory,
        request.device_path,
        request.plic,
    )
    firmware = image_directory / "firmware.elf"
    content = firmware.read_bytes()
    symbol = read_symbols(content)["witness_amp_run"]
    segment = next(
        segment
        for segment in admit_elf(content, platform.memory.firmware)
        if segment.address <= symbol.address < segment.address + segment.file_bytes
    )
    altered = bytearray(content)
    altered[segment.offset + symbol.address - segment.address] ^= 1
    firmware.write_bytes(altered)
    image_path = image_directory / "image.json"
    image = json.loads(image_path.read_bytes())
    image["firmware_sha256"] = sha256_of_file(firmware)
    image_path.write_text(json.dumps(image), encoding="ascii")
    retain_revised_outer_hashes(directory)
    result = analyze_copy(directory)
    assert result.returncode == 1
    assert "compiled AMP contract bytes differ" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "reanalysis").exists()
