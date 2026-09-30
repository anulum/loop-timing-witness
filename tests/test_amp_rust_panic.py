# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual target Rust panic refusal through the public capture CLI

"""Exercise the linked Rust panic handler with an isolated source-bound fault image."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from amp_image_options import verification_arguments
from prepare_amp_image import BuildInputs, prepare_image
from test_amp_spike_command import REQUEST

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = Path("runtime/bare_metal/rust_kernel/src/lib.rs")
RESET = "unsafe { state.write(PidState::default()) };"
PANIC = 'let _ = state; panic!("injected reset panic");'


@pytest.fixture(scope="module")
def panic_image(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build an actual RV64 image whose public reset enters the original panic handler.

    Parameters
    ----------
    tmp_path_factory
        Exclusive original source and output allocation.

    Returns
    -------
    Path
        Verified ISA image retaining the isolated faulted Rust source and original inputs.
    """
    base = Path(os.environ["WITNESS_AMP_IMAGE"])
    directory = tmp_path_factory.mktemp("rust-panic")
    source = directory / "source"
    source.mkdir()
    for name in ("controllers", "runtime", "tools", "src"):
        shutil.copytree(
            ROOT / name,
            source / name,
            ignore=shutil.ignore_patterns("target", "__pycache__", ".pytest_cache"),
        )
    shutil.copyfile(ROOT / "Makefile", source / "Makefile")
    adapter = source / ADAPTER
    original = adapter.read_text(encoding="utf-8")
    assert original.count(RESET) == 1, "original public reset implementation changed"
    adapter.write_text(original.replace(RESET, PANIC), encoding="utf-8")
    assert sha256_of_file(ROOT / ADAPTER) != sha256_of_file(adapter)
    compiler = Path(os.environ["WITNESS_RV64_CC"])
    image = directory / "image"
    prepare_image(
        BuildInputs(
            root=source,
            dtb=base / "platform.dtb",
            configuration=base / "configuration.txt",
            compiler=compiler,
            isa=True,
            rust_compiler="rustc",
        ),
        image,
        REQUEST,
    )
    assert sha256_of_file(image / "source" / ADAPTER) == sha256_of_file(adapter)
    with (directory / "make.log").open("wb") as log:
        subprocess.run(
            ["make", "-C", str(image), "-j2"],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=120,
        )
    return image


@pytest.mark.parametrize("plant", ["mechanical", "thermal"])
def test_public_target_rust_panic_refuses_before_first_sample(
    panic_image: Path, tmp_path: Path, plant: str
) -> None:
    """Require the real Rust panic to publish cause 0x109 on both production plants.

    Parameters
    ----------
    panic_image
        Actual source-bound RV64 firmware with a panic at the public reset entry point.
    tmp_path
        Exclusive public capture and retained simulator log.
    plant
        Original thermal or mechanical fabric model.
    """
    image = panic_image
    output = tmp_path / "capture"
    selection = verification_arguments(REQUEST)
    selection[selection.index("platform.dtb")] = str(image / "platform.dtb")
    selection[selection.index("configuration.txt")] = str(image / "configuration.txt")
    plugin = os.environ[
        "WITNESS_SPIKE_THERMAL_PLUGIN" if plant == "thermal" else "WITNESS_SPIKE_PLUGIN"
    ]
    command = [
        sys.executable,
        "tools/capture_amp_simulation.py",
        *selection,
        "--image",
        str(image),
        "--output",
        str(output),
        "--spike",
        os.environ["WITNESS_SPIKE"],
        "--plugin",
        plugin,
        "--rtc-nanoseconds",
        "100",
        "--time-limit",
        "100000000",
        "--timeout",
        "60",
    ]
    (tmp_path / "command.txt").write_text("\n".join(command) + "\n", encoding="utf-8")
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=75, check=False
    )
    (tmp_path / "cli.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AMP firmware refused or telemetry overflowed: cause=265 value=0" in (
        output / "spike.log"
    ).read_text(encoding="utf-8")
    assert "WITNESS_AMP_COMPLETION" not in (output / "spike.log").read_text(encoding="utf-8")
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
    assert not (output / "reports").exists()
    assert not (output / "events.bin").read_bytes()
    assert len((output / "tracking_raw.csv").read_text(encoding="utf-8").splitlines()) == 1
