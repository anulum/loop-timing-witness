# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public C/Rust RV64 capture parity on production RTL plants

"""Build current Rust firmware and plugins, then compare actual C/Rust capture streams."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from amp_image_options import verification_arguments
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ParityAssets:
    """Current compiled C/Rust images, two production plugins and exclusive output root."""

    directory: Path
    c_image: Path
    rust_image: Path
    plugins: tuple[Path, Path]


def _selection(image: Path) -> list[str]:
    """Select the original resource contract and captured DTB/configuration for an image.

    Parameters
    ----------
    image
        Original verified public image directory.

    Returns
    -------
    list of str
        Public image/capture argument vector for its original runtime topology.
    """
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(image / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(image / "configuration.txt")
    return arguments


def _run(command: list[str], log: Path, timeout: int) -> None:
    """Execute one real public build or capture command and retain its complete output.

    Parameters
    ----------
    command
        Original public CLI or Make invocation.
    log
        Exclusive diagnostic path for the command.
    timeout
        Bounded host wall-clock seconds.
    """
    with log.open("xb") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    assert result.returncode == 0, log.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parity_assets(tmp_path_factory: pytest.TempPathFactory) -> ParityAssets:
    """Build Rust firmware and both RTL plugins against the actual CI C image and Spike SDK.

    Parameters
    ----------
    tmp_path_factory
        Exclusive real firmware and native build allocation.

    Returns
    -------
    ParityAssets
        Current public image and plugin paths for both arithmetic backends.
    """
    directory = tmp_path_factory.mktemp("public-c-rust-parity")
    c_image = Path(os.environ["WITNESS_AMP_IMAGE"])
    compiler = os.environ["WITNESS_RV64_CC"]
    source = os.environ["WITNESS_SPIKE_SOURCE"]
    sdk = os.environ["WITNESS_SPIKE_BUILD"]
    rust_image = directory / "rust-image"
    _run(
        [
            sys.executable,
            "tools/prepare_amp_image.py",
            *_selection(c_image),
            "--output",
            str(rust_image),
            "--compiler",
            compiler,
            "--isa",
            "--rust-compiler",
            "rustc",
        ],
        directory / "rust-prepare.log",
        120,
    )
    _run(["make", "-C", str(rust_image), "-j2"], directory / "rust-build.log", 180)
    c_preparation = json.loads((c_image / "preparation.json").read_bytes())
    rust_preparation = json.loads((rust_image / "preparation.json").read_bytes())
    assert "kernel_backend" not in c_preparation
    assert rust_preparation["kernel_backend"] == "rust"
    plugins = (directory / "mechanical-plugin", directory / "thermal-plugin")
    for thermal, plugin in enumerate(plugins):
        _run(
            [
                "make",
                "amp-spike-plugin",
                f"AMP_SPIKE_SOURCE={source}",
                f"AMP_SPIKE_BUILD={sdk}",
                f"AMP_PLUGIN_DIRECTORY={plugin}",
                f"SIMULATION_THERMAL={thermal}",
            ],
            directory / f"plugin-{thermal}.log",
            180,
        )
    return ParityAssets(directory, c_image, rust_image, plugins)


def _report_rows(path: Path) -> list[dict[str, str]]:
    """Read observed interval rows without each capture's unique run identifier.

    Parameters
    ----------
    path
        Public installed analyzer CSV report.

    Returns
    -------
    list of dict of str to str
        Ordered observed rows for comparison between arithmetic backends.
    """
    with path.open(newline="", encoding="utf-8") as stream:
        return [
            {name: value for name, value in row.items() if name != "run_id"}
            for row in csv.DictReader(stream)
        ]


@pytest.mark.parametrize(("thermal", "plant"), [(0, "mechanical"), (1, "thermal")])
def test_public_c_rust_capture_parity(
    parity_assets: ParityAssets, thermal: int, plant: str
) -> None:
    """Require ten real C/Rust samples and equal telemetry/tracking on each production plant.

    Parameters
    ----------
    parity_assets
        Current public firmware and compiled native/RTL plugins.
    thermal
        Actual compiled plant parameter.
    plant
        Human-readable plant name used for exclusive output paths.
    """
    plugin = parity_assets.plugins[thermal] / "witness_spike_axi.so"
    captures = []
    for backend, image in [("c", parity_assets.c_image), ("rust", parity_assets.rust_image)]:
        output = parity_assets.directory / f"{backend}-{plant}-capture"
        _run(
            [
                sys.executable,
                "tools/capture_amp_simulation.py",
                *_selection(image),
                "--image",
                str(image),
                "--output",
                str(output),
                "--spike",
                os.environ["WITNESS_SPIKE"],
                "--plugin",
                str(plugin),
                "--rtc-nanoseconds",
                "100",
                "--time-limit",
                "100000000",
                "--timeout",
                "60",
            ],
            parity_assets.directory / f"{backend}-{plant}.log",
            90,
        )
        receipt = json.loads((output / "capture.json").read_bytes())
        assert receipt["completion"] == {
            "samples": 10,
            "events": 40,
            "misses": 0,
            "overflow": 0,
            "safe": False,
            "thermal": bool(thermal),
        }
        assert receipt["physical_verified"] is False
        captures.append(output)
    c_capture, rust_capture = captures
    for name in ["events.bin", "tracking_raw.csv", "tracking.csv"]:
        assert (c_capture / name).read_bytes() == (rust_capture / name).read_bytes()
    for name in ["reports/cycle_intervals.csv", "reports/interval_summary.csv"]:
        assert _report_rows(c_capture / name) == _report_rows(rust_capture / name)
