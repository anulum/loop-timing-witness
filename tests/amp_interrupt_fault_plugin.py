# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Spike post-arm interrupt identity fault build

"""Build a post-arm interrupt-identity fault from original production inputs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from amp_elf_symbols import read_symbols

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def interrupt_fault_sources(directory: Path, interrupt_address: int) -> tuple[Path, Path]:
    """Generate a plugin that changes expected interrupt identity after target arming.

    Parameters
    ----------
    directory
        Exclusive build directory for the generated diagnostic sources.
    interrupt_address
        Actual ELF address of the platform interrupt word.

    Returns
    -------
    tuple of Path and Path
        Generated plugin translation unit and diagnostic RAM transport header. Exact
        production anchors make source drift fail before compilation.
    """
    transport = (ROOT / "runtime/isa/spike_amp_transport.h").read_text()
    transport = transport.replace(
        '#include "../rtl/simulation.h"',
        '#include "' + str((ROOT / "runtime/rtl/simulation.h").resolve()) + '"',
    ).replace(
        '#include "../bare_metal/amp_contract.h"',
        '#include "' + str((ROOT / "runtime/bare_metal/amp_contract.h").resolve()) + '"',
    )
    anchor = """    /** Decode actual target little-endian bytes through the real RAM load entry. */
    std::uint32_t read_memory32(std::uint64_t address) {"""
    assert transport.count(anchor) == 1
    transport = transport.replace(
        anchor,
        """    /** Corrupt one test-owned target word after firmware interrupt setup. */
    void write_actual_word(std::uint64_t address, std::uint32_t value) {
        if (address < ram_base || address - ram_base > ram->size() - 4 || address % 4)
            throw std::invalid_argument("diagnostic target word outside actual RAM");
        std::array<std::uint8_t, 4> bytes{};
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(value >> (index * 8));
        if (!ram->store(address - ram_base, bytes.size(), bytes.data()))
            throw std::runtime_error("diagnostic target RAM store refused");
    }

"""
        + anchor,
    )
    transport_path = directory / "interrupt_fault_transport.h"
    transport_path.write_text(transport)

    source = (ROOT / "runtime/isa/spike_axi_device.cpp").read_text()
    replacements = {
        "../rtl/simulation.h": str((ROOT / "runtime/rtl/simulation.h").resolve()),
        "spike_amp_transport.h": str(transport_path.resolve()),
        "../amp_logger.h": str((ROOT / "runtime/amp_logger.h").resolve()),
    }
    for original_include, replacement in replacements.items():
        include = '"' + original_include + '"'
        assert source.count(include) == 1
        source = source.replace(include, '"' + replacement + '"')
    state = "    bool complete = false;"
    assert source.count(state) == 1
    source = source.replace(state, state + "\n    bool identity_corrupted = false;")
    poll = "            complete = logger.poll();"
    assert source.count(poll) == 1
    source = source.replace(
        poll,
        poll
        + """
            if (!identity_corrupted &&
                transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, status)) == WITNESS_AMP_ARMED) {
                transport.write_actual_word("""
        + str(interrupt_address)
        + """, UINT32_C(3));
                identity_corrupted = true;
            }""",
    )
    source_path = directory / "interrupt_fault_plugin.cpp"
    source_path.write_text(source)
    return source_path, transport_path


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def interrupt_fault_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Link the diagnostic identity mutation against verified production objects."""
    production = Path(os.environ[request.param])
    receipt = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest

    firmware = Path(os.environ["WITNESS_AMP_IMAGE"]) / "firmware.elf"
    symbol = read_symbols(firmware.read_bytes())["witness_amp_platform"]
    assert symbol.size == 56
    interrupt_address = symbol.address + 4
    directory = tmp_path_factory.mktemp("amp-interrupt-fault-plugin")
    source, transport = interrupt_fault_sources(directory, interrupt_address)
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
                "interrupt_address": interrupt_address,
                "production_plugin": receipt["plugin_sha256"],
                "production_transport": sha256_of_file(ROOT / "runtime/isa/spike_amp_transport.h"),
                "diagnostic_transport": sha256_of_file(transport),
                "diagnostic_source": sha256_of_file(source),
                "diagnostic_plugin": sha256_of_file(target),
            },
            indent=2,
        )
    )
    return target
