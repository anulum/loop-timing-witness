# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Spike post-release startup admission faults

"""Build one explicit startup-admission diagnostic from production inputs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from amp_elf_symbols import read_symbols

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def startup_admission_fault_sources(
    directory: Path, platform_address: int, mmio_address: int
) -> tuple[Path, Path]:
    """Generate a plugin that changes one real post-release target observation.

    Parameters
    ----------
    directory
        Exclusive directory for generated diagnostic sources.
    platform_address
        Address of the actual firmware platform contract.
    mmio_address
        Bound production Witness AXI aperture base.

    Returns
    -------
    tuple of Path and Path
        Diagnostic plugin translation unit and RAM transport header.
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
        """    /** Change one target word after the production logger releases startup. */
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
    transport_path = directory / "startup_admission_fault_transport.h"
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
    source = source.replace("#include <charconv>", "#include <charconv>\n#include <cstdlib>")
    settings_end = """    std::string run_path, event_path, tracking_path;
};"""
    assert source.count(settings_end) == 1
    source = source.replace(
        settings_end,
        settings_end
        + """

/** Select one explicit diagnostic without changing the production run file. */
std::string diagnostic_fault() {
    const auto *selection = std::getenv("WITNESS_STARTUP_ADMISSION_FAULT");
    if (!selection || !*selection)
        throw std::invalid_argument("startup-admission diagnostic fault is required");
    return selection;
}""",
    )
    members = """    witness::AmpLogger<witness::SpikeAmpTransport> logger;
    bool complete = false;"""
    assert source.count(members) == 1
    source = source.replace(
        members,
        """    witness::AmpLogger<witness::SpikeAmpTransport> logger;
    const std::string fault = diagnostic_fault();
    bool complete = false, injected = false;
    unsigned armed_status_reads = 0;""",
    )
    load = """        const auto reply = fabric.read(static_cast<std::uint8_t>(address));
        synchronize();
        if (reply.response != 0) return false;
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(reply.data >> (index * 8));"""
    assert source.count(load) == 1
    source = source.replace(
        load,
        """        const auto reply = fabric.read(static_cast<std::uint8_t>(address));
        synchronize();
        if (reply.response != 0) return false;
        auto observed = reply.data;
        if (injected) {
            if (fault == "version" && address == 0x7c) observed = 0;
            else if (fault == "sample-width" && address == 0x78) observed = 23;
            else if (fault == "period" && address == 0x40) observed += 1;
            else if (fault == "cycles" && address == 0x3c) observed += 1;
            else if (fault == "startup-status" && address == 4) observed = 2;
            else if (fault == "logger-status" && address == 4)
                transport.write_actual_word(configuration.shared +
                    offsetof(witness_amp_mailbox, logger_status), 99);
            else if (fault == "submit-blocked" && address == 4 &&
                     transport.read_memory32(configuration.shared +
                         offsetof(witness_amp_mailbox, status)) == WITNESS_AMP_ARMED &&
                     ++armed_status_reads % 2 == 0) observed = 4;
        }
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(observed >> (index * 8));""",
    )
    poll = """        if (!complete) {
            complete = logger.poll();
            if (complete) {"""
    assert source.count(poll) == 1
    source = source.replace(
        poll,
        """        if (!complete) {
            if (injected && fault != "submit-blocked") {
                if (transport.read_memory32(configuration.shared +
                        offsetof(witness_amp_mailbox, status)) == WITNESS_AMP_REFUSED)
                    throw std::runtime_error("ACTUAL_STARTUP_ADMISSION_REFUSAL cause=" +
                        std::to_string(transport.read_memory32(configuration.shared +
                            offsetof(witness_amp_mailbox, trap_cause))) + " value=" +
                        std::to_string(transport.read_memory32(configuration.shared +
                            offsetof(witness_amp_mailbox, trap_value))));
            } else {
                complete = logger.poll();
            }
            if (!injected && transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, logger_status)) == WITNESS_AMP_LOGGER_READY) {
                const auto shared = configuration.shared;
                if (fault == "abi")
                    transport.write_actual_word(shared + offsetof(witness_amp_mailbox, abi), 0);
                else if (fault == "mailbox-status")
                    transport.write_actual_word(shared + offsetof(witness_amp_mailbox, status), 1);
                else if (fault == "producer")
                    transport.write_actual_word(
                        shared + offsetof(witness_amp_mailbox, producer), 1);
                else if (fault == "consumer")
                    transport.write_actual_word(
                        shared + offsetof(witness_amp_mailbox, consumer), 1);
                else if (fault == "overflow")
                    transport.write_actual_word(
                        shared + offsetof(witness_amp_mailbox, telemetry_overflow), 1);
                else if (fault == "samples")
                    transport.write_actual_word(shared + offsetof(witness_amp_mailbox, samples), 1);
                else if (fault == "trap-cause")
                    transport.write_actual_word(
                        shared + offsetof(witness_amp_mailbox, trap_cause), 1);
                else if (fault == "trap-value")
                    transport.write_actual_word(
                        shared + offsetof(witness_amp_mailbox, trap_value), 1);
                else if (fault == "enable-word") {
                    transport.write_actual_word("""
        + str(platform_address + 24)
        + ", "
        + str(mmio_address + 0x7C)
        + """U);
                    transport.write_actual_word("""
        + str(platform_address + 28)
        + """, 0U);
                }
                injected = true;
            }
            if (complete) {""",
    )
    source_path = directory / "startup_admission_fault_plugin.cpp"
    source_path.write_text(source)
    return source_path, transport_path


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def startup_admission_fault_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Link the diagnostic against hash-verified production RTL and SDK objects."""
    production = Path(os.environ[request.param])
    receipt = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest

    firmware = Path(os.environ["WITNESS_AMP_IMAGE"]) / "firmware.elf"
    symbols = read_symbols(firmware.read_bytes())
    directory = tmp_path_factory.mktemp("amp-startup-admission-fault-plugin")
    source, transport = startup_admission_fault_sources(
        directory, symbols["witness_amp_platform"].address, 0x40000000
    )
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
                "production_plugin": receipt["plugin_sha256"],
                "production_source": sha256_of_file(ROOT / "runtime/isa/spike_axi_device.cpp"),
                "production_transport": sha256_of_file(ROOT / "runtime/isa/spike_amp_transport.h"),
                "diagnostic_source": sha256_of_file(source),
                "diagnostic_transport": sha256_of_file(transport),
                "diagnostic_plugin": sha256_of_file(target),
            },
            indent=2,
        )
    )
    return target
