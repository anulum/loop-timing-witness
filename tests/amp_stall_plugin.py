# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Spike consumer scheduling fault build

"""Build an explicit scheduling fault against the original production SDK and RTL objects."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def scheduling_source() -> str:
    """Copy the original plugin and suspend telemetry polling after its first actual consumption.

    Returns
    -------
    str
        Diagnostic source that retains original target execution, RTL and event draining,
        reads actual RAM after refusal and never writes producer-owned state. Exact original
        scheduling anchors must occur once; changed production source fails explicitly.
    """
    source = (ROOT / "runtime/isa/spike_axi_device.cpp").read_text()
    for include in ["../rtl/simulation.h", "spike_amp_transport.h", "../amp_logger.h"]:
        source = source.replace(
            '"' + include + '"', '"' + str((ROOT / "runtime/isa" / include).resolve()) + '"'
        )
    state = "bool complete = false;"
    assert source.count(state) == 1
    source = source.replace(state, state + "\n    witness::RunResult stalled_events;")
    original = "        if (!complete) {\n            complete = logger.poll();"
    assert source.count(original) == 1
    replacement = """        if (!complete) {
            const auto status = transport.read_memory32(configuration.shared +
                offsetof(witness_amp_mailbox, status));
            const auto consumed = transport.read_memory32(configuration.shared +
                offsetof(witness_amp_mailbox, consumer));
            if (consumed && status != WITNESS_AMP_REFUSED) {
                witness::drain_available(transport, output, stalled_events);
                return;
            }
            if (status == WITNESS_AMP_REFUSED) {
                std::cerr << "ACTUAL_STALLED_MAILBOX";
                for (std::size_t offset = 0; offset < sizeof(witness_amp_mailbox); offset += 4)
                    std::cerr << " " << transport.read_memory32(configuration.shared + offset);
                std::cerr << "\\n";
            }
            complete = logger.poll();"""
    return source.replace(original, replacement)


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def stall_plugin(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile and link a genuine scheduling variant using the selected original build receipt.

    Parameters
    ----------
    request
        Original mechanical or thermal production plugin environment key.
    tmp_path_factory
        Exclusive generated source, dependency records, build logs and diagnostic shared object.

    Returns
    -------
    Path
        Diagnostic plugin linked against hash-verified original native and RTL objects.
        No production source, original SDK or installed object is changed.
    """
    production = Path(os.environ[request.param])
    receipt = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest
    directory = tmp_path_factory.mktemp("amp-stall-plugin")
    source = directory / "consumer_stall.cpp"
    source.write_text(scheduling_source())
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
                "original": sha256_of_file(ROOT / "runtime/isa/spike_axi_device.cpp"),
                "diagnostic": sha256_of_file(source),
                "plugin": sha256_of_file(target),
            },
            indent=2,
        )
    )
    return target
