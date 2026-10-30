# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict public capture acquisition

"""Acquire capture files through no-follow descriptors and reuse the complete decoder."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .neural_capture import NeuralCaptureConfiguration, NeuralChannelFiles, load_neural_capture
from .neural_run_files import read_neural_run_file

if TYPE_CHECKING:
    from .neural_capture import NeuralCaptureBundle


def bind_neural_capture(
    directory: Path, manifest: dict[str, Any], tool: dict[str, Any]
) -> NeuralCaptureBundle:
    """Decode only the original bytes acquired through the strict public file reader.

    Parameters
    ----------
    directory
        Immutable source-admitted original acquisition root.
    manifest, tool
        Closed public declarations and complete actual tool references.

    Returns
    -------
    NeuralCaptureBundle
        The established complete capture interpretation, with original bytes,
        projections, counters and all independent loss/identity/timing findings.
    """
    configuration = NeuralCaptureConfiguration(
        manifest["step_count"],
        manifest["completion"]["observed_service_packets"],
        manifest["capture_horizon_edges"],
    )
    declarations = [
        NeuralChannelFiles(item["role"], item["capture"], item["payload"], item["markers"])
        for item in manifest["channels"]
    ]
    originals = [(tool["counter_receipt"], 4096)]
    for item in manifest["channels"]:
        population = (
            configuration.service_packets if item["role"] == "service" else configuration.step_count
        )
        originals.extend(
            [
                (item["capture"], (population + 2) * 16),
                (item["payload"], population * 16),
                (item["markers"], 32),
            ]
        )
    with tempfile.TemporaryDirectory(prefix="neural-capture-") as name:
        root = Path(name)
        for reference, allocation in originals:
            raw = read_neural_run_file(directory, reference, allocation)
            target = root / reference["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        return load_neural_capture(
            root,
            (declarations[0], declarations[1], declarations[2]),
            tool["counter_receipt"],
            configuration,
        )
