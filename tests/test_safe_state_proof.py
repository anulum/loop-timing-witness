# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — deadline monitor safe-state proofs

"""Prove the deadline monitor's safe-state invariants by temporal induction with Yosys."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled, scaled_seconds

if TYPE_CHECKING:
    from pathlib import Path


def test_safe_state_invariants_hold_and_their_negation_fails(tmp_path: Path) -> None:
    """Each miss limit's invariants are proven; the never-latches negation has a counterexample.

    Parameters
    ----------
    tmp_path
        Exclusive proof, netlist and counterexample output allocation.
    """
    result = subprocess.run(
        [
            "make",
            "safe-state-invariants",
            f"SAFE_STATE_DIRECTORY={tmp_path}",
            f"SAT_TIMEOUT={scaled_seconds(30)}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(150),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for limit in (1, 3, 255):
        assert "Induction step proven: SUCCESS!" in (tmp_path / f"limit-{limit}.log").read_text()
        netlist = json.loads((tmp_path / f"limit-{limit}.json").read_text())
        assert any(name.startswith(("deadline_monitor", "$paramod")) for name in netlist["modules"])
    assert "SAT proof finished - model found: FAIL!" in (tmp_path / "negative.log").read_text()
    assert json.loads((tmp_path / "counterexample.json").read_text())["signal"]
