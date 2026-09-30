# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual ISA receipt custody and public run manifest regression

"""Rebuild actual production plugins against original Spike headers and execute their RTL."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from capture_amp_simulation import main as capture_main
from test_capture_amp_simulation import ROOT, capture_arguments

__all__ = ["capture_arguments"]


@pytest.mark.parametrize("thermal", [0, 1])
def test_public_plugin_build_and_capture(capture_arguments: list[str], thermal: int) -> None:
    """Build all real native/RTL inputs and require the public capture to observe that model.

    Parameters
    ----------
    capture_arguments
        Actual verified image and installed matching Spike executable.
    thermal
        Concrete production RTL plant parameter selected for a fresh build.
    """
    source = os.environ.get("WITNESS_SPIKE_SOURCE")
    build = os.environ.get("WITNESS_SPIKE_BUILD")
    assert source is not None, "matching original Spike source is required"
    assert build is not None, "matching actual generated Spike headers are required"
    image = Path(capture_arguments[capture_arguments.index("--image") + 1])
    output = image.parent / "plugin-build"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + source,
            "AMP_SPIKE_BUILD=" + build,
            "AMP_PLUGIN_DIRECTORY=" + str(output),
            "SIMULATION_THERMAL=" + str(thermal),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    (image.parent / "plugin-build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    capture_arguments[capture_arguments.index("--plugin") + 1] = str(
        output / "witness_spike_axi.so"
    )
    assert capture_main(capture_arguments) == 0
    capture = Path(capture_arguments[capture_arguments.index("--output") + 1])
    receipt = json.loads((capture / "capture.json").read_bytes())
    assert receipt["completion"]["thermal"] is bool(thermal)
    assert receipt["completion"]["samples"] == 10
    assert receipt["physical_verified"] is False


@pytest.mark.parametrize("fault", ["source", "build", "empty"])
def test_missing_original_sdk_refused(tmp_path: Path, fault: str) -> None:
    """Fail the real Make entry before build output when explicit original SDK inputs are absent.

    Parameters
    ----------
    tmp_path
        Owned path for checking that admission did not create outputs.
    fault
        Absent original source, generated headers or both required selections.
    """
    source = os.environ.get("WITNESS_SPIKE_SOURCE")
    build = os.environ.get("WITNESS_SPIKE_BUILD")
    assert source is not None
    assert build is not None
    output = tmp_path / "refused-build"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE="
            + (
                ""
                if fault == "empty"
                else str(tmp_path / "absent")
                if fault == "source"
                else source
            ),
            "AMP_SPIKE_BUILD="
            + ("" if fault == "empty" else str(tmp_path / "absent") if fault == "build" else build),
            "AMP_PLUGIN_DIRECTORY=" + str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()
