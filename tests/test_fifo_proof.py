# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dual-clock event buffer proofs

"""Check the dual-clock event buffer's occupancy and data rules with Yosys from reset."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled, scaled_seconds

if TYPE_CHECKING:
    from pathlib import Path


def test_buffer_rules_hold_from_reset_and_their_negation_fails(tmp_path: Path) -> None:
    """Occupancy and data rules hold over every clock interleaving; never-full has a counterexample.

    Parameters
    ----------
    tmp_path
        Exclusive proof logs and counterexample.
    """
    result = subprocess.run(
        [
            "make",
            "fifo-invariants",
            f"FIFO_PROOF_DIRECTORY={tmp_path}",
            f"SAT_TIMEOUT={scaled_seconds(240)}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(600),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("occupancy", "data"):
        assert (
            "SAT proof finished - no model found: SUCCESS!"
            in (tmp_path / f"{name}.log").read_text()
        )
    assert "SAT proof finished - model found: FAIL!" in (tmp_path / "negative.log").read_text()
    # Yosys writes the waveform with escaped signal names that strict JSON refuses; its trace of
    # the filled buffer is checked by presence and size.
    assert (tmp_path / "counterexample.json").stat().st_size > 0
