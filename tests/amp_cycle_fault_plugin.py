# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Spike cycle-observation fault build

"""Build explicit cycle-observation faults from original production inputs."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
CycleFault = Literal["out-of-range", "repeated"]


@dataclass(frozen=True)
class CycleFaultPlugin:
    """One diagnostic plugin and the exact cycle observation it corrupts."""

    path: Path
    fault: CycleFault


def cycle_fault_source(directory: Path, fault: CycleFault) -> Path:
    """Generate a diagnostic plugin that corrupts one actual cycle-register response.

    Parameters
    ----------
    directory
        Exclusive build directory for the generated diagnostic source.
    fault
        Out-of-range first cycle or repeated second cycle.

    Returns
    -------
    Path
        Generated plugin translation unit. Exact production anchors make source drift
        fail before compilation.
    """
    source = (ROOT / "runtime/isa/spike_axi_device.cpp").read_text()
    replacements = {
        "../rtl/simulation.h": str((ROOT / "runtime/rtl/simulation.h").resolve()),
        "spike_amp_transport.h": str((ROOT / "runtime/isa/spike_amp_transport.h").resolve()),
        "../amp_logger.h": str((ROOT / "runtime/amp_logger.h").resolve()),
    }
    for original_include, replacement in replacements.items():
        anchor = '"' + original_include + '"'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '"' + replacement + '"')
    original = """        if (reply.response != 0)
            return false;
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(reply.data >> (index * 8));"""
    assert source.count(original) == 1
    corruption = "run.cycles" if fault == "out-of-range" else "(reply.data == 1 ? 0 : reply.data)"
    source = source.replace(
        original,
        """        if (reply.response != 0) return false;
        const auto observed = address == 0x10 ? """
        + corruption
        + """ : reply.data;
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(observed >> (index * 8));""",
    )
    source_path = directory / "cycle_fault_plugin.cpp"
    source_path.write_text(source)
    return source_path


@pytest.fixture(
    scope="module",
    params=[
        pytest.param(
            (environment, fault),
            id=environment.removeprefix("WITNESS_SPIKE_").lower() + "-" + fault,
        )
        for environment in ("WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN")
        for fault in ("out-of-range", "repeated")
    ],
)
def cycle_fault_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> CycleFaultPlugin:
    """Link one diagnostic MMIO reader against verified production objects."""
    environment, fault = request.param
    production = Path(os.environ[environment])
    receipt = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest

    directory = tmp_path_factory.mktemp("amp-cycle-fault-plugin")
    source = cycle_fault_source(directory, fault)
    sdk_source = Path(receipt["spike_sdk"]["source"])
    sdk_build = Path(receipt["spike_sdk"]["build"])
    verilator = Path(receipt["verilator"]["root"]) / "include"
    includes = [
        verilator,
        verilator / "vltstd",
        sdk_source,
        sdk_source / "riscv",
        sdk_source / "fdt",
        sdk_build,
    ]
    target = directory / "witness_spike_axi.so"
    commands = [
        [
            compiler["path"],
            "-std=c++20",
            "-O2",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-I" + str(production.parent / "rtl"),
            *[argument for path in includes for argument in ["-isystem", str(path)]],
            "-MD",
            "-MF",
            str(directory / "plugin.d"),
            "-c",
            str(source),
            "-o",
            str(directory / "plugin.o"),
        ],
        [
            compiler["path"],
            "-shared",
            "-Wl,--fatal-warnings",
            str(directory / "plugin.o"),
            *[name for name in receipt["link_inputs"] if Path(name).name != "plugin.o"],
            "-pthread",
            "-o",
            str(target),
        ],
    ]
    (directory / "build.argv.json").write_text(json.dumps(commands, indent=2))
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
        (directory / f"build_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    (directory / "source_sha256.json").write_text(
        json.dumps(
            {
                "fault": fault,
                "production_plugin": receipt["plugin_sha256"],
                "production_source": sha256_of_file(ROOT / "runtime/isa/spike_axi_device.cpp"),
                "diagnostic_source": sha256_of_file(source),
                "diagnostic_plugin": sha256_of_file(target),
            },
            indent=2,
        )
    )
    return CycleFaultPlugin(target, fault)
