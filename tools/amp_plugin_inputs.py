# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original native plugin generation inputs

"""Identify original SDK, RTL, handwritten sources and selected native build tools."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from amp_build_toolchain import (
    compiler_identity,
    program_identity,
    runtime_libraries,
    spike_sdk_identity,
    verilator_identity,
)

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
NATIVE_OBJECTS = ("controller", "configuration", "plugin", "verilated", "verilated_threads")
MAX_FIFO_ADDRESS_BITS = 14


@dataclass(frozen=True)
class PluginBuild:
    """Explicit original SDK, native compilers and production RTL parameters.

    Parameters
    ----------
    directory
        Exclusive native/model output directory.
    source
        Original matching Spike source checkout.
    sdk
        Original generated Spike SDK headers.
    cc
        Selected actual C driver.
    cxx
        Selected actual C++ driver, also used for generated model compilation.
    thermal
        Production RTL plant selection, zero or one.
    fifo_address_bits
        Actual compiled event FIFO address width.
    runtime_root
        Explicit compiler runtime root, which must match the actual Verilator installation.
    """

    directory: Path
    source: Path
    sdk: Path
    cc: str
    cxx: str
    thermal: int
    fifo_address_bits: int = 8
    runtime_root: Path | None = None


_PLUGIN_TOOLS = (
    "amp_plugin_inputs.py",
    "amp_plugin_preparation.py",
    "write_amp_plugin_manifest.py",
    "amp_build_dependencies.py",
    "amp_build_toolchain.py",
    "amp_tool_runtime.py",
    "manifest_io.py",
)


def _check_parameters(build: PluginBuild) -> None:
    """Refuse a plant mode other than zero or one and an out-of-range FIFO width.

    Parameters
    ----------
    build
        Requested plugin build.

    Raises
    ------
    ValueError
        If the thermal mode or the FIFO address width is invalid.
    """
    if type(build.thermal) is not int or build.thermal not in (0, 1):
        message = "AMP plugin thermal parameter must be zero or one"
        raise ValueError(message)
    if (
        type(build.fifo_address_bits) is not int
        or not 1 <= build.fifo_address_bits <= MAX_FIFO_ADDRESS_BITS
    ):
        message = "AMP plugin FIFO address bits must be in [1,14]"
        raise ValueError(message)


def _build_sources(build: PluginBuild, runtime: Path) -> list[Path]:
    """List every source, header, tool and package file the plugin build reads.

    Parameters
    ----------
    build
        Requested plugin build with its SDK and plugin sources.
    runtime
        Verilator installation root.

    Returns
    -------
    list[Path]
        Build files, RTL, C/C++ sources and headers, plugin tools and the
        installed package's Python and JSON files.
    """
    sources = [
        ROOT / "Makefile",
        ROOT / "amp-plugin-build.schema.json",
        ROOT / "runtime/isa/spike_plugin.mk",
        build.sdk / "config.h",
        runtime / "include/verilated.mk",
        runtime / "bin/verilator_includer",
    ]
    sources.extend((ROOT / "rtl").glob("*.sv"))
    for directory in (ROOT / "controllers/c", ROOT / "runtime", build.source, runtime / "include"):
        sources.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in (".h", ".hpp", ".c", ".cpp", ".inc")
        )
    sources.extend(ROOT / "tools" / name for name in _PLUGIN_TOOLS)
    # The installed package implementations and schemas are actual Python build inputs.
    sources.extend(
        path
        for path in (ROOT / "src/loop_timing_witness").rglob("*")
        if path.is_file() and (path.suffix in (".py", ".json") or path.name == "py.typed")
    )
    return sources


def _programs(
    build_tools: dict[str, Any], verilator: dict[str, Any], compilers: dict[str, Any]
) -> list[Path]:
    """Return every executable whose runtime libraries the build depends on.

    Parameters
    ----------
    build_tools
        Make, ar, Python and Perl identities.
    verilator
        Verilator identity with its backend.
    compilers
        C and C++ compiler identities.

    Returns
    -------
    list[Path]
        Build tools, the Verilator backend and every compiler driver and program.
    """
    programs = [Path(item["path"]) for item in build_tools.values()]
    programs.append(Path(verilator["backend"]["path"]))
    for compiler in compilers.values():
        programs.extend(
            Path(item["path"]) for item in [compiler["driver"], *compiler["programs"].values()]
        )
    return programs


def original_identity(build: PluginBuild) -> dict[str, Any]:
    """Freeze actual original sources and tools before RTL generation.

    Parameters
    ----------
    build
        Explicit original selections used by the public Make target.

    Returns
    -------
    dict of str to Any
        Original source/header hashes, SDK revision/patch and actual tool identities.

    Raises
    ------
    ValueError
        If concrete plant or event FIFO parameters are invalid.
    """
    _check_parameters(build)
    verilator = verilator_identity()
    runtime = Path(verilator["root"])
    if build.runtime_root is not None and build.runtime_root.resolve() != runtime:
        message = "AMP plugin runtime root differs from the actual Verilator installation"
        raise ValueError(message)
    sources = _build_sources(build, runtime)
    compilers = {
        "c": compiler_identity(build.cc, "cc1"),
        "cxx": compiler_identity(build.cxx, "cc1plus"),
    }
    build_tools = {
        **{name: program_identity(name) for name in ("make", "ar")},
        "python3": program_identity(sys.executable),
        "perl": program_identity("/usr/bin/perl"),
    }
    libraries = runtime_libraries(_programs(build_tools, verilator, compilers))
    return {
        "working_directory": str(ROOT),
        "thermal": build.thermal,
        "fifo_address_bits": build.fifo_address_bits,
        "compilers": compilers,
        "verilator": verilator,
        "spike_sdk": spike_sdk_identity(build.source, build.sdk),
        "build_tools": build_tools,
        "runtime_libraries": libraries,
        "sources": {
            **{str(path.resolve()): sha256_of_file(path) for path in sorted(set(sources))},
            **libraries,
        },
    }
