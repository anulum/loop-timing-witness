# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — diagnostic Spike plugin build from verified production objects

"""Verify a production plugin receipt and link one diagnostic source against its objects."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def verified_receipt(production: Path) -> dict[str, Any]:
    """Read the production plugin receipt and require every digest it binds.

    Parameters
    ----------
    production
        Production plugin, beside its ``plugin.json`` receipt.

    Returns
    -------
    dict[str, Any]
        Receipt whose plugin, compiler driver and link inputs match their digests.
    """
    receipt: dict[str, Any] = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest
    return receipt


def build_diagnostic_plugin(
    production: Path, receipt: dict[str, Any], directory: Path, source: Path
) -> Path:
    """Compile one diagnostic source and link it with the production objects.

    Parameters
    ----------
    production
        Production plugin, beside its RTL model directory.
    receipt
        Verified production plugin receipt.
    directory
        Exclusive build directory for the object, dependency records, argv and logs.
    source
        Diagnostic C++ source.

    Returns
    -------
    Path
        Linked diagnostic plugin.
    """
    target = directory / "witness_spike_axi.so"
    commands = _commands(production, receipt, directory, source)
    (directory / "build.argv.json").write_text(json.dumps(commands, indent=2))
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
        (directory / f"build_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    return target


def _commands(
    production: Path, receipt: dict[str, Any], directory: Path, source: Path
) -> list[list[str]]:
    """Return the strict compile command and the shared-object link command.

    A counted base plugin passes its recorded instrumentation on: the diagnostic object gets
    the same compile flags after the strict ones and the link the same link flags, so the
    production headers it includes are counted, while its own copied source, outside
    ``runtime/``, gets no counters.

    Parameters
    ----------
    production
        Production plugin, beside its RTL model directory.
    receipt
        Verified production plugin receipt.
    directory
        Build directory.
    source
        Diagnostic C++ source.

    Returns
    -------
    list[list[str]]
        Compile, then link, argument vectors.
    """
    compiler = receipt["compilers"]["cxx"]["driver"]
    includes = _includes(receipt)
    strict = ["-std=c++20", "-O2", "-fPIC", "-Wall", "-Wextra", "-Werror", "-Wconversion"]
    record = receipt.get("instrumentation", {"compile_flags": [], "link_flags": []})
    return [
        [
            compiler["path"],
            *strict,
            "-Wshadow",
            *record["compile_flags"],
            "-I" + str(production.parent / "rtl"),
            *[argument for path in includes for argument in ["-isystem", str(path)]],
            *("-MD", "-MF", str(directory / "plugin.d")),
            *("-c", str(source), "-o", str(directory / "plugin.o")),
        ],
        [
            compiler["path"],
            "-shared",
            *record["link_flags"],
            "-Wl,--fatal-warnings",
            str(directory / "plugin.o"),
            *[name for name in receipt["link_inputs"] if Path(name).name != "plugin.o"],
            "-pthread",
            "-o",
            str(directory / "witness_spike_axi.so"),
        ],
    ]


def _includes(receipt: dict[str, Any]) -> list[Path]:
    """Return the Verilator and Spike SDK system include directories of the receipt.

    Parameters
    ----------
    receipt
        Verified production plugin receipt.

    Returns
    -------
    list[Path]
        Include directories in compiler order.
    """
    sdk_source = Path(receipt["spike_sdk"]["source"])
    sdk_build = Path(receipt["spike_sdk"]["build"])
    verilator = Path(receipt["verilator"]["root"]) / "include"
    return [
        verilator,
        verilator / "vltstd",
        sdk_source,
        sdk_source / "riscv",
        sdk_source / "fdt",
        sdk_build,
    ]


def replace_once(source: str, anchor: str, replacement: str) -> str:
    """Replace one production anchor that must occur exactly once.

    Parameters
    ----------
    source
        Device source text.
    anchor
        Exact production text.
    replacement
        Diagnostic text.

    Returns
    -------
    str
        Changed source.
    """
    assert source.count(anchor) == 1
    return source.replace(anchor, replacement)


def transport_header() -> str:
    """Return the production RAM transport header with its includes made absolute.

    Returns
    -------
    str
        Header text whose refusal, simulation and contract includes name the
        repository files.
    """
    transport = (ROOT / "runtime/isa/spike_amp_transport.h").read_text()
    return (
        transport.replace(
            '#include "../refusal.h"',
            '#include "' + str((ROOT / "runtime/refusal.h").resolve()) + '"',
        )
        .replace(
            '#include "../rtl/simulation.h"',
            '#include "' + str((ROOT / "runtime/rtl/simulation.h").resolve()) + '"',
        )
        .replace(
            '#include "../bare_metal/amp_contract.h"',
            '#include "' + str((ROOT / "runtime/bare_metal/amp_contract.h").resolve()) + '"',
        )
    )


def device_source(transport: Path, logger: Path) -> str:
    """Return the production device source with each include made absolute exactly once.

    Parameters
    ----------
    transport
        RAM transport header to include, production or diagnostic.
    logger
        Logger header to include, production or diagnostic.

    Returns
    -------
    str
        Device source text.
    """
    source = (ROOT / "runtime/isa/spike_axi_device.cpp").read_text()
    replacements = {
        "../refusal.h": str((ROOT / "runtime/refusal.h").resolve()),
        "../rtl/simulation.h": str((ROOT / "runtime/rtl/simulation.h").resolve()),
        "spike_amp_transport.h": str(transport.resolve()),
        "../amp_logger.h": str(logger.resolve()),
    }
    for original_include, replacement in replacements.items():
        include = '"' + original_include + '"'
        assert source.count(include) == 1
        source = source.replace(include, '"' + replacement + '"')
    return source


def word_writer_transport(purpose: str) -> str:
    """Return the transport header with a checked target RAM word writer added.

    Parameters
    ----------
    purpose
        Documentation sentence of the added ``write_actual_word`` member.

    Returns
    -------
    str
        Header text, the writer inserted before the real RAM word reader.
    """
    transport = transport_header()
    anchor = """    /** Decode actual target little-endian bytes through the real RAM load entry. */
    std::uint32_t read_memory32(std::uint64_t address) {"""
    assert transport.count(anchor) == 1
    return transport.replace(
        anchor,
        "    /** "
        + purpose
        + """ */
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
