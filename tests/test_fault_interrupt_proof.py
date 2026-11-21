# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fault injector and retained interrupt proofs

"""Prove the fault injector's and the retained interrupt's rules by induction with Yosys."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled, scaled_seconds

if TYPE_CHECKING:
    from pathlib import Path

INDUCTION_PROVEN = "Induction step proven: SUCCESS!"
BASE_CASE_FAILS = "SAT temporal induction proof finished - model found for base case: FAIL!"
COUNTEREXAMPLE = "SAT proof finished - model found: FAIL!"


def run_proof(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run ``make fault-interrupt-invariants`` with its logs in ``directory``.

    Parameters
    ----------
    directory
        Exclusive directory for the proof logs, netlists and counterexamples.
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
            "fault-interrupt-invariants",
            f"FAULT_INTERRUPT_DIRECTORY={directory}",
            f"SAT_TIMEOUT={scaled_seconds(240)}",
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(600),
    )


def faulty_copy(directory: Path, source: str, original: str, replacement: str) -> Path:
    """Write a copy of one RTL source that differs from it in one line.

    Parameters
    ----------
    directory
        Exclusive directory that receives the copy.
    source
        Repository path of the RTL source.
    original
        The line to replace, which must occur exactly once.
    replacement
        The faulty line.

    Returns
    -------
    Path
        The faulty copy, under the source's file name.
    """
    text = (REPOSITORY_ROOT / source).read_text()
    assert text.count(original) == 1
    copy = directory / source.rsplit("/", 1)[-1]
    copy.write_text(text.replace(original, replacement))
    return copy


def test_injector_and_interrupt_rules_hold_and_their_negations_fail(tmp_path: Path) -> None:
    """Induction proves both units' rules; each negative control has a counterexample.

    Parameters
    ----------
    tmp_path
        Exclusive proof logs, netlists and counterexamples.
    """
    result = run_proof(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    for log in ("fault-2.log", "fault-100000.log", "interrupt.log"):
        assert INDUCTION_PROVEN in (tmp_path / log).read_text(), log
    for log in ("fault-negative.log", "interrupt-negative.log"):
        assert COUNTEREXAMPLE in (tmp_path / log).read_text(), log
    for trace in ("fault-counterexample.json", "interrupt-counterexample.json"):
        # Yosys writes the waveform with escaped signal names that strict JSON refuses; each
        # trace is checked by presence and size.
        assert (tmp_path / trace).stat().st_size > 0
    for netlist, unit in (
        ("fault-2.json", "fault_injector"),
        ("fault-100000.json", "fault_injector"),
        ("interrupt.json", "retained_interrupt"),
    ):
        modules = json.loads((tmp_path / netlist).read_text())["modules"]
        assert any(name == unit or name.startswith(f"$paramod\\{unit}\\") for name in modules)


def test_an_injector_whose_delayed_interrupt_comes_early_is_refused(tmp_path: Path) -> None:
    """The proof refuses an injector that raises the delayed interrupt one tick early.

    Parameters
    ----------
    tmp_path
        Faulty injector copy and its proof logs.
    """
    faulty = faulty_copy(
        tmp_path,
        "rtl/fault_injector.sv",
        "assign delayed_interrupt = remaining == 64'd1 && active_kind == 2'd1;",
        "assign delayed_interrupt = remaining == 64'd2 && active_kind == 2'd1;",
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    result = run_proof(logs, f"FAULT_PROOF_INJECTOR={faulty}", "FAULT_PROOF_PERIODS=2")
    assert result.returncode != 0
    log = (logs / "fault-2.log").read_text()
    assert BASE_CASE_FAILS in log
    assert INDUCTION_PROVEN not in log


def test_an_interrupt_that_accepts_an_acknowledge_without_a_snapshot_is_refused(
    tmp_path: Path,
) -> None:
    """The proof refuses an interrupt whose acknowledge does not require a held snapshot.

    Parameters
    ----------
    tmp_path
        Faulty interrupt copy and its proof logs.
    """
    faulty = faulty_copy(
        tmp_path,
        "rtl/retained_interrupt.sv",
        "local_write_strobes == 4'hf && observed_valid) local_response = 0;",
        "local_write_strobes == 4'hf) local_response = 0;",
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    result = run_proof(logs, f"INTERRUPT_PROOF_SOURCE={faulty}", "FAULT_PROOF_PERIODS=2")
    assert result.returncode != 0
    log = (logs / "interrupt.log").read_text()
    assert BASE_CASE_FAILS in log
    assert INDUCTION_PROVEN not in log
