# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capture levels enter bus synchronisers from registers

"""Require each capture level that a bus synchroniser samples to come straight from a register."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from pathlib import Path

SCRIPT = REPOSITORY_ROOT / "rtl/check_synchroniser_inputs.ys"
# Each earlier combinational form: source, register text, combinational text, refusing assertion.
COMBINATIONAL = {
    "quiescence": (
        "rtl/control_plant_witness.sv",
        (
            "    always_ff @(posedge capture_clock or negedge reset_n) begin\n"
            "        if (!reset_n) capture_quiescent <= 1'b0;\n"
            "        else capture_quiescent <= finished && !record_valid && !pps_valid"
            " && event_mask == 0;\n"
            "    end\n"
        ),
        (
            "    assign capture_quiescent = reset_n && finished && !record_valid && !pps_valid\n"
            "        && event_mask == 0;\n"
        ),
        "w:window.capture_quiescent %ci2 t:$adff %i",
    ),
    "pulse per second": (
        "rtl/control_plant_witness.sv",
        "            pps_stage <= {pps_stage[0], pps_in};\n",
        "            pps_stage <= {pps_stage[0], pps_in && !finished};\n",
        "w:pps_in %co1 t:$adff %i",
    ),
    "reset permission": (
        "rtl/axi_control_witness.sv",
        ".capture_reset_allowed(capture_reset_allowed)",
        ".capture_reset_allowed(!run_enabled || run_finished)",
        "w:reset_control.capture_reset_allowed %ci2 t:$adff %i",
    ),
}


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the synchroniser input check on the RTL tree under a root.

    Parameters
    ----------
    root
        Directory holding the ``rtl`` tree that the script reads.

    Returns
    -------
    subprocess.CompletedProcess of str
        Finished Yosys run with its captured output.
    """
    return subprocess.run(
        ["yosys", "-Q", "-T", "-q", "-s", str(SCRIPT)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(120),
    )


def test_production_synchroniser_inputs_are_registers() -> None:
    """Accept the production RTL: every checked synchroniser input is a register output."""
    result = _check(REPOSITORY_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("variant", sorted(COMBINATIONAL))
def test_combinational_synchroniser_input_is_refused(tmp_path: Path, variant: str) -> None:
    """Refuse a combinational form of each synchroniser input.

    Parameters
    ----------
    tmp_path
        Copy of the RTL tree holding the combinational variant.
    variant
        Which synchroniser input takes a combinational form: an earlier one, or logic between
        the pulse-per-second pin and its first synchroniser stage.
    """
    source, register, combinational, assertion = COMBINATIONAL[variant]
    shutil.copytree(REPOSITORY_ROOT / "rtl", tmp_path / "rtl")
    path = tmp_path / source
    text = path.read_text(encoding="utf-8")
    assert text.count(register) == 1
    path.write_text(text.replace(register, combinational), encoding="utf-8")
    result = _check(tmp_path)
    assert result.returncode != 0
    refusal = "Assertion failed: selection contains 0 elements instead of the asserted 1: "
    assert refusal + assertion in result.stdout + result.stderr
