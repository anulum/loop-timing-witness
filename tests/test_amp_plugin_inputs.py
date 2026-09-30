# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual pre-generation source and parameter admission

"""Freeze genuine native tool/SDK selections and reject invalid production RTL parameters."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from amp_plugin_inputs import PluginBuild, original_identity
from test_write_amp_plugin_manifest import original_plugin

from manifest_io import sha256_of_file

__all__ = ["original_plugin"]


def test_actual_generation_inputs(original_plugin: PluginBuild) -> None:
    """Bind all actual RTL/SDK/runtime originals and native frontend/backend tools.

    Parameters
    ----------
    original_plugin
        Actual public Make build against the original SDK.
    """
    data = original_identity(original_plugin)
    assert data["fifo_address_bits"] == 8
    assert data["thermal"] == 0
    assert any(name.endswith("sampled_plant.sv") for name in data["sources"])
    assert any(name.endswith("verilator_includer") for name in data["sources"])
    assert data["verilator"]["backend"]["version"]
    for item in data["build_tools"].values():
        assert item["version"]
        assert sha256_of_file(Path(item["path"])) == item["sha256"]


@pytest.mark.parametrize(
    ("thermal", "bits", "finding"),
    [(2, 8, "thermal"), (True, 8, "thermal"), (0, 0, "FIFO"), (0, 15, "FIFO"), (0, True, "FIFO")],
)
def test_actual_invalid_parameters(
    original_plugin: PluginBuild, thermal: int, bits: int, finding: str
) -> None:
    """Refuse invalid concrete plant/FIFO selections before the original tools execute.

    Parameters
    ----------
    original_plugin
        Actual native build selection.
    thermal
        Explicit candidate plant parameter.
    bits
        Explicit candidate FIFO address width.
    finding
        Specific refusal required by the RTL parameter contract.
    """
    with pytest.raises(ValueError, match=finding):
        original_identity(replace(original_plugin, thermal=thermal, fifo_address_bits=bits))


@pytest.mark.parametrize("matching", [True, False])
def test_selected_runtime_root(original_plugin: PluginBuild, *, matching: bool) -> None:
    """Require explicitly selected compiler runtime headers to match the real generator.

    Parameters
    ----------
    original_plugin
        Actual public native build against the installed generator.
    matching
        Whether to retain its actual runtime root or request the unrelated SDK directory.
    """
    receipt = json.loads((original_plugin.directory / "plugin.json").read_bytes())
    runtime = Path(receipt["verilator"]["root"]) if matching else original_plugin.sdk
    selected = replace(original_plugin, runtime_root=runtime)
    if matching:
        assert original_identity(selected)["verilator"] == receipt["verilator"]
    else:
        with pytest.raises(ValueError, match="runtime root differs"):
            original_identity(selected)
