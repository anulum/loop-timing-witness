# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual zero-claim machine-external trap

"""Execute a real empty PLIC claim before the unchanged target lifecycle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_logger import FLAGS
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def spurious_claim_image(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, Path]:
    """Link a zero-claim prelude around the original target main entry."""
    image = tmp_path_factory.mktemp("amp-spurious-claim-target") / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    shutil.copy2(ROOT / "tests/native/amp_spurious_claim.c", image / "spurious_claim.c")
    compiler = os.environ["WITNESS_RV64_CC"]
    commands = [
        [
            compiler,
            *FLAGS,
            "-Isource",
            "-MD",
            "-MF",
            "objects/spurious_claim.o.d",
            "-c",
            "spurious_claim.c",
            "-o",
            "objects/spurious_claim.o",
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
            *["objects/input_" + str(index) + ".o" for index in range(5)],
            "objects/spurious_claim.o",
            "-Wl,--wrap=witness_amp_main",
            "-o",
            "firmware.elf",
        ],
    ]
    (image / "spurious_claim_build.argv.json").write_text(json.dumps(commands, indent=2))
    for index, command in enumerate(commands):
        result = subprocess.run(command, cwd=image, capture_output=True, text=True, check=False)
        (image / f"spurious_claim_build_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    return image, Path(os.environ[request.param])


def test_actual_zero_plic_claim_returns_to_complete_run(
    tmp_path: Path, spurious_claim_image: tuple[Path, Path]
) -> None:
    """Require an empty real claim to return before the original ten-cycle run.

    Parameters
    ----------
    tmp_path
        Exclusive simulator command and raw completed outputs.
    spurious_claim_image
        Original target image with a source-bound wrapper and selected production plant.
    """
    image, plugin = spurious_claim_image
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
    assert 'WITNESS_AMP_COMPLETION {"samples":10,"events":40' in result.stdout
    assert (output / "events.bin").stat().st_size == 640
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
