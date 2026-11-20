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
from pathlib import Path
from string import Template

import pytest
from amp_diagnostic_build import (
    build_diagnostic_plugin,
    device_source,
    replace_once,
    verified_receipt,
    word_writer_transport,
)
from amp_elf_symbols import read_symbols

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


# Exact production anchors and their diagnostic replacements in the device source.
_SETTINGS_END = """    std::string run_path, event_path, tracking_path;
};"""
_SELECTOR = """

/** Select one explicit diagnostic without changing the production run file. */
std::string diagnostic_fault() {
    const auto *selection = std::getenv("WITNESS_STARTUP_ADMISSION_FAULT");
    if (!selection || !*selection)
        throw std::invalid_argument("startup-admission diagnostic fault is required");
    return selection;
}"""
_MEMBERS = """    witness::AmpLogger<witness::SpikeAmpTransport> logger;
    bool complete = false;"""
_MEMBERS_FAULT = """    witness::AmpLogger<witness::SpikeAmpTransport> logger;
    const std::string fault = diagnostic_fault();
    bool complete = false, injected = false;
    unsigned armed_status_reads = 0;"""
_LOAD = """        const auto reply = fabric.read(static_cast<std::uint16_t>(address));
        synchronize();
        if (reply.response != 0)
            return false;
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(reply.data >> (index * 8));"""
_LOAD_OBSERVED = """        const auto reply = fabric.read(static_cast<std::uint16_t>(address));
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
            bytes[index] = static_cast<std::uint8_t>(observed >> (index * 8));"""
_POLL = """        if (!complete) {
            complete = logger.poll();
            if (complete) {"""
_POLL_INJECTION = Template(
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
                    transport.write_actual_word(${enable_address}, ${enable_value}U);
                    transport.write_actual_word(${next_address}, 0U);
                }
                injected = true;
            }
            if (complete) {"""
)


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
    transport = word_writer_transport(
        "Change one target word after the production logger releases startup."
    )
    transport_path = directory / "startup_admission_fault_transport.h"
    transport_path.write_text(transport)
    source = device_source(transport_path, ROOT / "runtime/amp_logger.h")
    source = source.replace("#include <charconv>", "#include <charconv>\n#include <cstdlib>")
    source = replace_once(source, _SETTINGS_END, _SETTINGS_END + _SELECTOR)
    source = replace_once(source, _MEMBERS, _MEMBERS_FAULT)
    source = replace_once(source, _LOAD, _LOAD_OBSERVED)
    injection = _POLL_INJECTION.substitute(
        enable_address=platform_address + 24,
        enable_value=mmio_address + 0x7C,
        next_address=platform_address + 28,
    )
    source = replace_once(source, _POLL, injection)
    source_path = directory / "startup_admission_fault_plugin.cpp"
    source_path.write_text(source)
    return source_path, transport_path


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def startup_admission_fault_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Link the diagnostic against hash-verified production RTL and SDK objects."""
    production = Path(os.environ[request.param])
    receipt = verified_receipt(production)

    firmware = Path(os.environ["WITNESS_AMP_IMAGE"]) / "firmware.elf"
    symbols = read_symbols(firmware.read_bytes())
    directory = tmp_path_factory.mktemp("amp-startup-admission-fault-plugin")
    source, transport = startup_admission_fault_sources(
        directory, symbols["witness_amp_platform"].address, 0x40000000
    )
    target = build_diagnostic_plugin(production, receipt, directory, source)
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
