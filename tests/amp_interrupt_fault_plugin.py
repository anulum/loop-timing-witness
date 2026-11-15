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
from pathlib import Path

import pytest
from amp_diagnostic_build import (
    build_diagnostic_plugin,
    device_source,
    verified_receipt,
    word_writer_transport,
)
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
    transport = word_writer_transport(
        "Corrupt one test-owned target word after firmware interrupt setup."
    )
    transport_path = directory / "interrupt_fault_transport.h"
    transport_path.write_text(transport)

    source = device_source(transport_path, ROOT / "runtime/amp_logger.h")
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
    receipt = verified_receipt(production)

    firmware = Path(os.environ["WITNESS_AMP_IMAGE"]) / "firmware.elf"
    symbol = read_symbols(firmware.read_bytes())["witness_amp_platform"]
    assert symbol.size == 56
    interrupt_address = symbol.address + 4
    directory = tmp_path_factory.mktemp("amp-interrupt-fault-plugin")
    source, transport = interrupt_fault_sources(directory, interrupt_address)
    target = build_diagnostic_plugin(production, receipt, directory, source)
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
