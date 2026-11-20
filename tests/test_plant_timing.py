# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — one-edge plant and reference products

"""Prove and exercise the one-edge products of the plant and the reference."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled, scaled_seconds

if TYPE_CHECKING:
    from pathlib import Path

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


def test_split_multiplier_public_port(run_rtl: RunRtl) -> None:
    """Compare every 8-bit pair and the 32-bit corner and random pairs one edge later.

    Parameters
    ----------
    run_rtl
        Public RTL simulation runner.
    """
    result = run_rtl("split_multiplier_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SPLIT_MULTIPLIER_PASS narrow=65536 wide=20400" in result.stdout


def test_plant_timing_proofs_and_counterexamples(tmp_path: Path) -> None:
    """Prove each timing invariant and require a counterexample to its negation.

    Parameters
    ----------
    tmp_path
        Exclusive proof, netlist and counterexample output allocation.
    """
    result = subprocess.run(
        [
            "make",
            "plant-timing-invariants",
            f"PLANT_TIMING_DIRECTORY={tmp_path}",
            f"SAT_TIMEOUT={scaled_seconds(30)}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(150),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for module, elaborated in (
        ("plant_spacing", "control_cycle"),
        ("plant_actuator", "deadline_monitor"),
        ("plant_configuration", "run_configuration_registers"),
        ("split_multiplier", "split_multiplier"),
    ):
        assert "Induction step proven: SUCCESS!" in (tmp_path / f"{module}.log").read_text()
        assert (
            "SAT proof finished - model found: FAIL!"
            in (tmp_path / f"{module}-negative.log").read_text()
        )
        assert json.loads((tmp_path / f"{module}-counterexample.json").read_text())["signal"]
        netlist = json.loads((tmp_path / f"{module}.json").read_text())
        assert any(
            name == elaborated or name.startswith(f"$paramod\\{elaborated}\\")
            for name in netlist["modules"]
        )
