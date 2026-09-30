# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public logger API on actual Spike RAM and production RTL

"""Exercise logger lifecycle and acquisition callbacks through the real ISA transport."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from amp_elf import admit_elf
from amp_elf_symbols import read_symbols
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

from manifest_io import sha256_of_file

if TYPE_CHECKING:
    from device_tree_resources import Region

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def logger_api_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Link API calls to unchanged logger code and hash-verified production model objects.

    Parameters
    ----------
    request
        Actual mechanical or thermal production plugin selection.
    tmp_path_factory
        Exclusive diagnostic source, dependency records and compiler output.

    Returns
    -------
    Path
        Actual Spike plugin whose additional calls use only the public logger API.
    """
    production = Path(os.environ[request.param])
    receipt = json.loads((production.parent / "plugin.json").read_bytes())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest
    directory = tmp_path_factory.mktemp("amp-logger-api-plugin")
    original = ROOT / "runtime/isa/spike_axi_device.cpp"
    source = original.read_text()
    for include, header_path in [
        ("../rtl/simulation.h", "runtime/rtl/simulation.h"),
        ("spike_amp_transport.h", "runtime/isa/spike_amp_transport.h"),
        ("../amp_logger.h", "runtime/amp_logger.h"),
    ]:
        anchor = f'#include "{include}"'
        assert source.count(anchor) == 1
        source = source.replace(anchor, f'#include "{ROOT / header_path}"')
    source = "#include <cstdlib>\n" + source
    members = "    witness::AmpLogger<witness::SpikeAmpTransport> logger;"
    assert source.count(members) == 1
    source = source.replace(
        members,
        """    const std::string mode = std::getenv("WITNESS_LOGGER_API");
    unsigned starts = 0, checks = 0, finishes = 0, arming_waits = 0, backlog_waits = 0;
    bool mailbox_faulted = false;
    const witness::RunHooks hooks{
        [this] {
            ++starts;
            if (mode == "start-failure") throw std::runtime_error("API start failure");
        },
        [this] {
            ++checks;
            if (mode == "check-failure") throw std::runtime_error("API check failure");
        },
        [this] {
            ++finishes;
            if (mode == "finish-failure") throw std::runtime_error("API finish failure");
        }
    };
    witness::AmpLogger<witness::SpikeAmpTransport> logger;""",
    )
    initialiser = "logger(transport, run, output, configuration.shared)"
    assert source.count(initialiser) == 1
    source = source.replace(initialiser, initialiser[:-1] + ", &hooks)")
    constructor = "        witness::configure_run(transport, run);\n        synchronize();"
    assert source.count(constructor) == 1
    source = source.replace(
        constructor,
        constructor
        + """
        if (mode == "contract") ++run.cycles;
        if (mode == "unready") (void)logger.completion();
        if (mode == "transport-zero" || mode == "transport-alignment" ||
            mode == "transport-overflow") {
            const auto address = mode == "transport-zero" ? 0ULL :
                mode == "transport-alignment" ? 1ULL : UINT64_MAX - 7ULL;
            witness::SpikeAmpTransport rejected(simulator, fabric, address);
        }
        if (mode == "memory-below") (void)transport.read_memory32(configuration.shared - 4);
        if (mode == "memory-above")
            (void)transport.read_memory32(configuration.shared + sizeof(witness_amp_mailbox));
        if (mode == "memory-alignment")
            (void)transport.read_memory32(configuration.shared + 1);
        if (mode == "write-owner") transport.write_memory32(configuration.shared, 0);
        if (mode == "write-below") transport.write_memory32(configuration.shared - 4, 0);
        if (mode == "transport-roundtrip") {
            const auto consumer = configuration.shared + offsetof(witness_amp_mailbox, consumer);
            transport.write_memory32(consumer, 0x78563412);
            if (transport.read_memory32(consumer) != 0x78563412)
                throw std::runtime_error("API actual little-endian RAM transfer differs");
            transport.write_memory32(consumer, 0);
            transport.write_memory32(configuration.shared +
                offsetof(witness_amp_mailbox, logger_status), 0);
            (void)transport.read_memory32(configuration.shared + sizeof(witness_amp_mailbox) - 4);
            std::cout << "API_MEMORY_ROUNDTRIP\\n";
        }
        if (mode == "factory-tree") {
            const std::vector<std::string> arguments{
                std::to_string(configuration.base), std::to_string(configuration.interrupt),
                std::to_string(configuration.rtc_nanoseconds),
                std::to_string(configuration.time_limit), std::to_string(configuration.shared),
                configuration.run_path, configuration.event_path, configuration.tracking_path};
            std::cout << "API_FACTORY_TREE\\n"
                      << mmio_device_map().at("witness_axi")->generate_dts(&simulator, arguments);
        }
        if (mode == "adapter-requests") {
            std::array<std::uint8_t, 4> bytes{};
            if (load(0, 1, bytes.data()) || load(256, 4, bytes.data()) ||
                load(1, 4, bytes.data()) || load(252, 4, bytes.data()) ||
                store(0, 1, bytes.data()) || store(256, 4, bytes.data()) ||
                store(1, 4, bytes.data()) || store(252, 4, bytes.data()))
                throw std::runtime_error("API invalid native AXI request admitted");
            if (!load(0x6c, 4, bytes.data()))
                throw std::runtime_error("API valid native AXI read refused");
            for (unsigned index = 0; index < 4; ++index)
                bytes[index] = static_cast<std::uint8_t>((run.cycles - 1) >> (index * 8));
            if (!store(0x3c, 4, bytes.data()))
                throw std::runtime_error("API valid native AXI write refused");
            std::cout << "API_ADAPTER_REQUESTS\\n";
        }
        if (mode == "mailbox-zero" || mode == "mailbox-alignment" || mode == "mailbox-overflow") {
            const auto address = mode == "mailbox-zero" ? 0ULL :
                mode == "mailbox-alignment" ? 1ULL : UINT64_MAX - 7ULL;
            witness::AmpLogger<witness::SpikeAmpTransport> rejected(
                transport, run, output, address);
        }""",
    )
    final = (
        "                if (!std::cout) "
        'throw std::runtime_error("AMP completion receipt write failed");'
    )
    assert source.count(final) == 1
    source = source.replace(
        final,
        final
        + """
                if (starts != 1 || !checks || finishes != 1)
                    throw std::runtime_error("API acquisition lifecycle differs");
                if (mode == "arming-wait" && !arming_waits)
                    throw std::runtime_error("API arming wait was not observed");
                if (mode == "backlog" && !backlog_waits)
                    throw std::runtime_error("API backlog wait was not observed");
                std::cout << "API_HOOKS " << starts << " " << checks << " " << finishes << "\\n";
                std::cout.flush();
                (void)logger.completion();
                if (mode == "repoll") (void)logger.poll();""",
    )
    entry = "    reg_t size() override { return 256; }"
    assert source.count(entry) == 1
    source = source.replace(
        entry,
        entry
        + """

    /** Damage one actual reserved RAM word through the public Spike memory API. */
    void damage_mailbox(std::size_t offset) {
        const auto address = configuration.shared + offset;
        for (const auto &mapping : simulator.get_bus().get_devices()) {
            auto *memory = dynamic_cast<abstract_mem_t *>(mapping.second);
            if (!memory || address < mapping.first) continue;
            const auto displacement = address - mapping.first;
            if (displacement > memory->size() || memory->size() - displacement < 4) continue;
            const std::array<std::uint8_t, 4> bytes{1, 0, 0, 0};
            if (!memory->store(displacement, bytes.size(), bytes.data()))
                throw std::runtime_error("API actual mailbox store refused");
            mailbox_faulted = true;
            return;
        }
        throw std::runtime_error("API actual mailbox mapping absent");
    }""",
    )
    polling = "            complete = logger.poll();"
    assert source.count(polling) == 1
    source = source.replace(
        polling,
        """            if (!mailbox_faulted && (mode.starts_with("fresh-") ||
                mode.starts_with("arm-") || mode == "overflow-only")) {
                const auto abi = transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, abi));
                const auto status = transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, status));
                if (abi == WITNESS_AMP_ABI && !starts &&
                    (mode.starts_with("fresh-") || mode == "overflow-only" ||
                     status == WITNESS_AMP_ARMED)) {
                    if (mode == "fresh-status")
                        damage_mailbox(offsetof(witness_amp_mailbox, status));
                    if (mode == "fresh-producer" || mode == "arm-producer")
                        damage_mailbox(offsetof(witness_amp_mailbox, producer));
                    if (mode == "fresh-consumer" || mode == "arm-consumer")
                        damage_mailbox(offsetof(witness_amp_mailbox, consumer));
                    if (mode == "fresh-trap-cause")
                        damage_mailbox(offsetof(witness_amp_mailbox, trap_cause));
                    if (mode == "fresh-trap-value")
                        damage_mailbox(offsetof(witness_amp_mailbox, trap_value));
                    if (mode == "fresh-samples")
                        damage_mailbox(offsetof(witness_amp_mailbox, samples));
                    if (mode == "fresh-logger-status")
                        damage_mailbox(offsetof(witness_amp_mailbox, logger_status));
                    if (mode == "overflow-only")
                        damage_mailbox(offsetof(witness_amp_mailbox, telemetry_overflow));
                }
            }
            if (mode == "backlog" && starts &&
                (!backlog_waits || transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, status)) != WITNESS_AMP_FINISHED)) {
                ++backlog_waits;
                return;
            }
"""
        + polling
        + """
            if (mode == "arming-wait" && !starts &&
                transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, logger_status)) == WITNESS_AMP_LOGGER_READY) {
                if (logger.poll()) throw std::runtime_error("API unexpected early completion");
                ++arming_waits;
            }""",
    )
    diagnostic = directory / "logger_api_plugin.cpp"
    diagnostic.write_text(source)
    sdk = receipt["spike_sdk"]
    verilator = Path(receipt["verilator"]["root"]) / "include"
    includes = [
        verilator,
        verilator / "vltstd",
        Path(sdk["source"]),
        Path(sdk["source"]) / "riscv",
        Path(sdk["source"]) / "fdt",
        Path(sdk["build"]),
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
            str(diagnostic),
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
            {"original": sha256_of_file(original), "diagnostic": sha256_of_file(diagnostic)},
            indent=2,
        )
    )
    return target


def lqr_diagnostic_image(original: Path, tmp_path: Path, reservation: Region) -> Path:
    """Retain an original ELF copy with its real LQR flag and matching native configuration.

    Parameters
    ----------
    original
        Source-bound actual RV64 image to preserve unchanged.
    tmp_path
        Exclusive diagnostic image and mutation receipt directory.
    reservation
        Complete admitted original firmware RAM extent for ELF symbol validation.

    Returns
    -------
    Path
        Actual diagnostic executable image with both original and changed hashes retained.
    """
    image = tmp_path / "lqr-image"
    shutil.copytree(original, image)
    firmware = image / "firmware.elf"
    data = firmware.read_bytes()
    address = read_symbols(data)["witness_amp_run"].address + 8
    segment = next(
        part
        for part in admit_elf(data, reservation)
        if part.address <= address and address + 4 <= part.address + part.file_bytes
    )
    offset = segment.offset + address - segment.address
    assert struct.unpack_from("<I", data, offset) == (0,)
    changed = bytearray(data)
    struct.pack_into("<I", changed, offset, 1)
    firmware.write_bytes(changed)
    configuration = image / "configuration.txt"
    words = configuration.read_text().split()
    assert words[0] == "pid"
    words[0] = "lqr"
    configuration.write_text(" ".join(words) + "\n")
    (image / "target-mutation.json").write_text(
        json.dumps(
            {
                "field": "witness_amp_run.lqr",
                "original_elf_sha256": sha256_of_file(original / "firmware.elf"),
                "elf_sha256": sha256_of_file(firmware),
                "configuration_sha256": sha256_of_file(configuration),
            },
            indent=2,
        )
    )
    return image


@pytest.mark.parametrize(
    ("mode", "finding"),
    [
        ("healthy", ""),
        ("lqr", ""),
        ("transport-roundtrip", ""),
        ("adapter-requests", ""),
        ("factory-tree", ""),
        ("arming-wait", ""),
        ("backlog", ""),
        ("mailbox-zero", "AMP mailbox address outside bounds"),
        ("mailbox-alignment", "AMP mailbox address outside bounds"),
        ("mailbox-overflow", "AMP mailbox address outside bounds"),
        ("contract", "AMP running firmware contract differs from logger configuration"),
        ("unready", "AMP run is not complete"),
        ("repoll", "AMP logger is already complete"),
        ("start-failure", "API start failure"),
        ("check-failure", "API check failure"),
        ("finish-failure", "API finish failure"),
        ("fresh-status", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-producer", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-consumer", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-trap-cause", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-trap-value", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-samples", "AMP firmware did not initialize a fresh mailbox"),
        ("fresh-logger-status", "AMP firmware did not initialize a fresh mailbox"),
        ("arm-consumer", "AMP firmware did not arm a fresh run"),
        ("arm-producer", "AMP firmware did not arm a fresh run"),
        ("overflow-only", "AMP firmware refused or telemetry overflowed: cause=0 value=0"),
        ("transport-zero", "AMP shared memory address outside bounds"),
        ("transport-alignment", "AMP shared memory address outside bounds"),
        ("transport-overflow", "AMP shared memory address outside bounds"),
        ("memory-below", "AMP memory access outside the reserved mailbox"),
        ("memory-above", "AMP memory access outside the reserved mailbox"),
        ("memory-alignment", "AMP memory access outside the reserved mailbox"),
        ("write-owner", "AMP logger cannot write firmware-owned memory"),
        ("write-below", "AMP logger cannot write firmware-owned memory"),
    ],
)
def test_public_logger_api(
    logger_api_plugin: Path, tmp_path: Path, mode: str, finding: str
) -> None:
    """Observe public API refusals and callbacks on actual firmware and RTL execution.

    Parameters
    ----------
    logger_api_plugin
        Diagnostic client of the unchanged production logger and real transport.
    tmp_path
        Exclusive raw execution outputs and complete diagnostics.
    mode
        Actual API argument, lifecycle violation or acquisition callback failure.
    finding
        Required failure; empty for the complete healthy lifecycle.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    if mode == "lqr":
        image = lqr_diagnostic_image(image, tmp_path, platform.memory.firmware)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), logger_api_plugin, 100, 10000000),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    environment = dict(os.environ)
    environment["WITNESS_LOGGER_API"] = mode
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    (output / "api_mode.json").write_text(json.dumps({"mode": mode}))
    result = subprocess.run(
        argv, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30, check=False
    )
    (output / "spike.log").write_text(result.stdout + result.stderr)
    if finding:
        assert result.returncode != 0
        assert finding in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
    if mode in {
        "healthy",
        "lqr",
        "arming-wait",
        "backlog",
        "repoll",
        "transport-roundtrip",
        "adapter-requests",
        "factory-tree",
    }:
        assert '"samples":10,"events":40,"misses":0,"overflow":0,"safe":false' in result.stdout
        assert "API_HOOKS 1 " in result.stdout
        assert (output / "events.bin").stat().st_size == 640
        assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    else:
        assert "WITNESS_AMP_COMPLETION" not in result.stdout
    if mode == "transport-roundtrip":
        assert "API_MEMORY_ROUNDTRIP" in result.stdout
    if mode == "adapter-requests":
        assert "API_ADAPTER_REQUESTS" in result.stdout
    if mode == "factory-tree":
        assert "API_FACTORY_TREE" in result.stdout
        assert "witness@40000000" in result.stdout
        assert 'compatible = "anulum,loop-timing-witness-axi-v1"' in result.stdout
        assert "interrupts = <0x2>" in result.stdout
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
