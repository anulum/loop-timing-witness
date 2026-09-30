# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual ISA receipt custody and public run manifest regression

"""Reject contradictory analysis declarations against original real dedicated-hart captures."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from analyze_run import build_report
from run_manifest import load_run
from test_amp_simulation_manifest import actual_capture, capture_arguments

from manifest_io import sha256_of_file

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["actual_capture", "capture_arguments"]


@pytest.mark.parametrize(
    "fault",
    ["directory", "controller", "period", "plant", "tracking", "overflow", "started", "unit"],
)
def test_contradictory_declaration_refused(actual_capture: Path, fault: str) -> None:
    """Refuse invented controller/plant metadata, revised observations and contrary final counters.

    Parameters
    ----------
    actual_capture
        Complete actual source-bound RV64 and production RTL capture.
    fault
        Contradictory analysis declaration while preserving actual original capture bytes.
    """
    path = actual_capture / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if fault == "directory":
        inputs = replace(load_run(path), directory=None)
        finding = "original hash-bound"
    else:
        if fault == "controller":
            manifest["controller"]["name"] = "lqr"
        elif fault == "period":
            manifest["sample_period_ticks"] *= 2
        elif fault == "plant":
            manifest["plant"]["name"] = "first_order_thermal"
        elif fault == "started":
            manifest["started_utc"] = "2026-09-26T00:00:00+00:00"
        elif fault == "unit":
            manifest["plant"]["tracking_unit"] = "fabricated unit"
        elif fault == "tracking":
            tracking = actual_capture / "tracking.csv"
            tracking.write_bytes(tracking.read_bytes().replace(b"0,1,0", b"0,2,0", 1))
            manifest["files"]["tracking"]["sha256"] = sha256_of_file(tracking)
        else:
            manifest["instrument"]["fifo_overflow_count"] = 1
        path.write_text(json.dumps(manifest), encoding="ascii")
        inputs = load_run(path)
        finding = "completion counters" if fault == "overflow" else "configuration"
    with pytest.raises(ValueError, match=finding):
        build_report(inputs)


@pytest.mark.parametrize("fault", ["sampling", "missing-sampling", "native", "power"])
def test_incompatible_amp_contract_refused(actual_capture: Path, fault: str) -> None:
    """Reject schema combinations that would mislabel real AMP observations or attach false power.

    Parameters
    ----------
    actual_capture
        Original complete actual simulation.
    fault
        Unsupported run declaration layered on otherwise admitted real captured inputs.
    """
    path = actual_capture / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if fault == "sampling":
        manifest["tracking_sampling"] = "complete"
    elif fault == "missing-sampling":
        del manifest["tracking_sampling"]
    elif fault == "native":
        manifest["native_metadata"] = manifest["amp_capture"]
    else:
        manifest["files"]["power"] = manifest["files"]["tracking"]
    path.write_text(json.dumps(manifest), encoding="ascii")
    with pytest.raises(ValueError, match="run manifest"):
        load_run(path)
