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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from amp_diagnostic_build import build_diagnostic_plugin, device_source, verified_receipt

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
    source = device_source(
        ROOT / "runtime/isa/spike_amp_transport.h", ROOT / "runtime/amp_logger.h"
    )
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
    receipt = verified_receipt(production)

    directory = tmp_path_factory.mktemp("amp-cycle-fault-plugin")
    source = cycle_fault_source(directory, fault)
    target = build_diagnostic_plugin(production, receipt, directory, source)
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
