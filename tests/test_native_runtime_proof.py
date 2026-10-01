# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native lifecycle source proofs and counterexample controls

"""Prove the real register sequence and latched states used by the native lifecycle."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def test_native_commit_and_state_proofs(tmp_path: Path) -> None:
    """Verify production-module proofs and a real counterexample to each false variant.

    Parameters
    ----------
    tmp_path
        Exclusive proof, elaborated-source and counterexample output allocation.
    """
    result = subprocess.run(
        ["make", "native-runtime-invariants", f"NATIVE_INVARIANT_DIRECTORY={tmp_path}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for module in (
        "runtime_commit",
        "runtime_enabled",
        "runtime_finished",
        "runtime_safe",
        "runtime_release",
    ):
        assert (
            "SAT proof finished - no model found: SUCCESS!"
            in (tmp_path / f"{module}.log").read_text()
        )
        assert (
            "SAT proof finished - model found: FAIL!"
            in (tmp_path / f"{module}-negative.log").read_text()
        )
        assert json.loads((tmp_path / f"{module}-counterexample.json").read_text())["signal"]
        netlist = json.loads((tmp_path / f"{module}.json").read_text())
        assert any(
            name in netlist["modules"]
            for name in (
                "control_io_registers",
                "run_configuration_registers",
                "control_cycle",
                "deadline_monitor",
                "clock_reset_release",
            )
        )
