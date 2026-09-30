# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — post-execution image, executable, library and receipt custody

"""Verify original execution inputs and runtime identities after the actual target exits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from amp_build_toolchain import simulator_identity
from amp_capture_snapshot import verify_snapshot
from amp_plugin_receipt import admit_plugin, decode_plugin_receipt
from amp_runtime_snapshot import validate_runtime_snapshot

from manifest_io import sha256_of_file

if TYPE_CHECKING:
    from pathlib import Path

    from amp_spike_command import SpikeTools


def verify_execution(
    output: Path,
    expected: dict[str, str],
    tools: SpikeTools,
    plugin_receipt: bytes,
    runtime: dict[str, Any],
) -> None:
    """Refuse changed captured images, executed binaries, loaded libraries or original receipts.

    Parameters
    ----------
    output
        Actual completed target output and original input snapshot directory.
    expected
        Original relative image input hashes.
    tools
        Actual selected simulator and admitted plugin.
    plugin_receipt
        Original admitted complete native plugin receipt bytes.
    runtime
        Original admitted actual simulator version and loaded library identities.

    Raises
    ------
    OSError
        If original or captured execution inputs are unavailable.
    ValueError
        If image, executable, library or original native receipt bytes changed during execution.
    """
    verify_snapshot(output / "image", expected)
    identities = {
        "spike": runtime["sha256"],
        "plugin": decode_plugin_receipt(plugin_receipt)["plugin_sha256"],
    }
    if identities != {
        "spike": sha256_of_file(tools.executable),
        "plugin": sha256_of_file(tools.plugin),
    }:
        message = "AMP simulator or plugin changed during execution"
        raise ValueError(message)
    validate_runtime_snapshot(output, runtime["runtime_libraries"])
    if simulator_identity(tools.executable, tools.plugin) != runtime:
        message = "AMP simulator runtime libraries or version changed during execution"
        raise ValueError(message)
    current_receipt, _ = admit_plugin(tools.plugin)
    if current_receipt != plugin_receipt:
        message = "AMP plugin build receipt changed during execution"
        raise ValueError(message)
