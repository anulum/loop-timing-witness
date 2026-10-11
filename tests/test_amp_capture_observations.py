# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original AMP observations and fault schedule conversion

"""Convert genuine C/Rust captures without rounding or inventing missing samples."""

from __future__ import annotations

import csv
import io
import json
from decimal import Inexact, localcontext
from fractions import Fraction
from typing import TYPE_CHECKING

import pytest
from test_amp_capture_scenarios import arithmetic_compiler, scenario_capture
from test_amp_simulation_manifest import actual_capture
from test_capture_amp_simulation import capture_arguments

from loop_timing_witness.amp_capture_observations import fault_schedule, tracking_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["actual_capture", "arithmetic_compiler", "capture_arguments", "scenario_capture"]


@pytest.mark.parametrize(
    "scenario_capture",
    [
        ("lqr", True, "none", 2),
        ("pid", False, "delay", 2),
        ("pid", False, "freeze", 4),
        ("lqr", True, "overload", 2),
    ],
    indirect=True,
)
def test_exact_observed_conversion(scenario_capture: Path) -> None:
    """Preserve actual Q8.24 rows and configured faults under hostile decimal precision.

    Parameters
    ----------
    scenario_capture
        Fresh actual C or Rust firmware execution with production mechanical or thermal RTL.
    """
    capture = json.loads((scenario_capture / "capture.json").read_bytes())
    configuration = (scenario_capture / "image/configuration.txt").read_bytes()
    words = configuration.decode("ascii").split()
    cycles = int(words[1])
    samples = capture["completion"]["samples"]
    original = (scenario_capture / "tracking_raw.csv").read_bytes()
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        converted = tracking_csv(original, cycles, samples)
        assert context.prec == 3
        assert context.traps[Inexact] is True
    assert converted == (scenario_capture / "tracking.csv").read_bytes()
    raw_rows = list(csv.DictReader(io.StringIO(original.decode("ascii"))))
    observed = list(csv.DictReader(io.StringIO(converted.decode("ascii"))))
    assert len(raw_rows) == len(observed) == samples
    assert any(int(row["output_raw"]) != 0 for row in raw_rows)
    for raw, row in zip(raw_rows, observed, strict=True):
        assert int(row["cycle"]) == int(raw["cycle"])
        assert Fraction(row["reference"]) == Fraction(int(raw["reference_raw"]), 1 << 24)
        assert Fraction(row["output"]) == Fraction(int(raw["output_raw"]), 1 << 24)
    schedule = fault_schedule(configuration)
    if words[19] == "none":
        assert schedule == []
    else:
        assert schedule == [
            {
                "cycle": 3,
                "kind": "overload_request" if words[19] == "overload" else words[19],
                "delay_periods": 2 if words[19] == "delay" else 0,
            }
        ]
    if words[19] == "freeze":
        assert samples < cycles
        assert [int(row["cycle"]) for row in observed] == [int(row["cycle"]) for row in raw_rows]


def test_incomplete_configuration_refused(actual_capture: Path) -> None:
    """Reject incomplete or non-ASCII original configuration through the converter API.

    Parameters
    ----------
    actual_capture
        Genuine complete AMP capture whose original files remain unmodified.
    """
    configuration = (actual_capture / "image/configuration.txt").read_bytes()
    incomplete = b" ".join(configuration.split()[:-1])
    with pytest.raises(ValueError, match="complete original native"):
        fault_schedule(incomplete)
    with pytest.raises(ValueError, match="must be ASCII"):
        fault_schedule(configuration + b"\xff")


def test_tracking_contradictions_refused(actual_capture: Path) -> None:
    """Reject invented sample counts and repeated actual rows before producing converted data.

    Parameters
    ----------
    actual_capture
        Genuine complete AMP capture whose original observations are retained.
    """
    original = (actual_capture / "tracking_raw.csv").read_bytes()
    words = (actual_capture / "image/configuration.txt").read_text().split()
    samples = json.loads((actual_capture / "capture.json").read_bytes())["completion"]["samples"]
    with pytest.raises(ValueError, match="sample count does not match"):
        tracking_csv(original, int(words[1]), samples + 1)
    lines = original.splitlines(keepends=True)
    lines[2] = lines[1]
    with pytest.raises(ValueError, match="unique and increasing"):
        tracking_csv(b"".join(lines), int(words[1]), samples)
