# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual ISA receipt custody and public run manifest regression

"""Exercise fresh dedicated-hart firmware faults and thermal RTL through public capture."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from capture_amp_simulation import main as capture_main
from prepare_amp_image import BuildInputs, prepare_image
from test_amp_spike_command import REQUEST
from test_capture_amp_simulation import ROOT, capture_arguments

__all__ = ["capture_arguments"]


@pytest.fixture(params=[None, "rustc"], ids=["c", "rust"])
def arithmetic_compiler(request: pytest.FixtureRequest) -> str | None:
    """Select each maintained actual firmware arithmetic implementation for every scenario.

    Parameters
    ----------
    request
        Explicit C default or installed original Rust compiler selector.

    Returns
    -------
    str or None
        Actual Rust selection, or the original default C arithmetic backend.
    """
    selected = request.param
    assert selected is None or isinstance(selected, str)
    return selected


@pytest.fixture
def scenario_capture(
    capture_arguments: list[str], request: pytest.FixtureRequest, arithmetic_compiler: str | None
) -> Path:
    """Compile a fresh original native scenario and execute its actual firmware and RTL.

    Parameters
    ----------
    capture_arguments
        Actual installed tools and original platform copy.
    request
        Explicit controller, plant and fault scenario supplied by the test.
    arithmetic_compiler
        Actual selected C or Rust arithmetic implementation.

    Returns
    -------
    Path
        Complete public capture and report produced by actual target execution.
    """
    controller, thermal, fault, periods = request.param
    original = Path(capture_arguments[capture_arguments.index("--image") + 1])
    words = (original / "configuration.txt").read_text().split()
    words[0] = controller
    words[19:24] = [fault, "3", str(periods), "100" if fault == "overload" else "0", "0"]
    if fault == "none":
        words[20:22] = ["0", "0"]
    configuration = original.parent / "scenario.txt"
    configuration.write_text(" ".join(words) + "\n", encoding="ascii")
    compiler = Path(json.loads((original / "preparation.json").read_bytes())["compiler"])
    image = original.parent / "scenario-image"
    prepare_image(
        BuildInputs(
            ROOT,
            original / "platform.dtb",
            configuration,
            compiler,
            isa=True,
            rust_compiler=arithmetic_compiler,
        ),
        image,
        REQUEST,
    )
    result = subprocess.run(
        ["make", "-C", str(image), "-j2"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name, value in (
        ("--image", image),
        ("--dtb", image / "platform.dtb"),
        ("--configuration", image / "configuration.txt"),
    ):
        capture_arguments[capture_arguments.index(name) + 1] = str(value)
    if thermal:
        plugin = os.environ.get("WITNESS_SPIKE_THERMAL_PLUGIN")
        assert plugin is not None, "actual production thermal RTL plugin is required"
        capture_arguments[capture_arguments.index("--plugin") + 1] = plugin
    assert capture_main(capture_arguments) == 0
    return Path(capture_arguments[capture_arguments.index("--output") + 1])


@pytest.mark.parametrize(
    "scenario_capture",
    [
        ("lqr", True, "none", 2),
        ("pid", False, "drop", 2),
        ("pid", False, "delay", 2),
        ("pid", False, "freeze", 2),
        ("pid", False, "freeze", 4),
        ("lqr", True, "overload", 2),
    ],
    indirect=True,
)
def test_actual_fault_and_plant_reports(scenario_capture: Path) -> None:
    """Require observed fault counters and declared controller/plant to follow actual execution.

    Parameters
    ----------
    scenario_capture
        Actual freshly compiled scenario and complete public capture.
    """
    capture = json.loads((scenario_capture / "capture.json").read_bytes())
    manifest = json.loads((scenario_capture / "manifest.json").read_bytes())
    report = json.loads((scenario_capture / "reports/report.json").read_bytes())
    words = (scenario_capture / "image/configuration.txt").read_text().split()
    assert manifest["controller"]["name"] == words[0]
    assert manifest["plant"]["name"] == (
        "first_order_thermal" if capture["completion"]["thermal"] else "second_order_mechanical"
    )
    assert report["amp_completion"] == capture["completion"]
    assert report["valid"] is False
    if words[19] == "none":
        assert manifest["fault_schedule"] == []
    else:
        schedule = manifest["fault_schedule"][0]
        assert schedule["cycle"] == 3
        assert schedule["kind"] == ("overload_request" if words[19] == "overload" else words[19])
        assert schedule["delay_periods"] == (2 if words[19] == "delay" else 0)
    if words[19] == "freeze" and words[21] == "4":
        assert capture["completion"]["safe"] is True
        assert capture["completion"]["misses"] == 7
        assert capture["completion"]["samples"] == 6
        assert report["events"]["control"]["observed_deadlines"] == 10
