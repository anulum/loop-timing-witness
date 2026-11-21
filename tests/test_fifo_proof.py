# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dual-clock event buffer proofs

"""Prove the dual-clock event buffer's occupancy and data rules by temporal induction with Yosys."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled, scaled_seconds

if TYPE_CHECKING:
    from pathlib import Path

CAPACITY_BITS = ("1", "2", "3", "4")
INDUCTION_PROVEN = "Induction step proven: SUCCESS!"


def run_proof(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run ``make fifo-invariants`` with its logs in ``directory``.

    Parameters
    ----------
    directory
        Exclusive directory for the proof logs and the counterexample.
    *arguments
        Further ``make`` variable assignments.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished ``make`` run with its captured output.
    """
    return subprocess.run(
        [
            "make",
            "fifo-invariants",
            f"FIFO_PROOF_DIRECTORY={directory}",
            f"SAT_TIMEOUT={scaled_seconds(240)}",
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(600),
    )


def test_buffer_rules_hold_in_every_reachable_state_and_their_negation_fails(
    tmp_path: Path,
) -> None:
    """Induction proves the rules at 2 to 16 records; never-full has a counterexample.

    Parameters
    ----------
    tmp_path
        Exclusive proof logs and counterexample.
    """
    result = run_proof(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for bits in CAPACITY_BITS:
        log = (tmp_path / f"induction-{bits}.log").read_text()
        assert "Base case for induction length 1 proven." in log
        assert INDUCTION_PROVEN in log
    assert "SAT proof finished - model found: FAIL!" in (tmp_path / "negative.log").read_text()
    # Yosys writes the waveform with escaped signal names that strict JSON refuses; its trace of
    # the filled buffer is checked by presence and size.
    assert (tmp_path / "counterexample.json").stat().st_size > 0


def test_a_buffer_that_writes_when_full_is_refused_with_a_trace(tmp_path: Path) -> None:
    """The same proof refuses a buffer whose write port ignores the full flag.

    The faulty copy differs from the buffer in one line, so the refusal shows that the observed
    registers are the buffer's own and that the proof reaches the overflow from reset.

    Parameters
    ----------
    tmp_path
        Faulty buffer copy and its proof logs.
    """
    buffer = (REPOSITORY_ROOT / "rtl/event_record_fifo.sv").read_text()
    guarded = "assign write_ready = write_reset_n && !write_full;"
    assert buffer.count(guarded) == 1
    faulty = tmp_path / "event_record_fifo.sv"
    faulty.write_text(buffer.replace(guarded, "assign write_ready = write_reset_n;"))
    logs = tmp_path / "logs"
    logs.mkdir()
    result = run_proof(logs, f"FIFO_PROOF_BUFFER={faulty}", "FIFO_PROOF_ADDRESS_BITS=1")
    assert result.returncode != 0
    log = (logs / "induction-1.log").read_text()
    assert "SAT temporal induction proof finished - model found for base case: FAIL!" in log
    assert INDUCTION_PROVEN not in log
