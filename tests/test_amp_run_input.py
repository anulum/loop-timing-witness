# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original native run input admission tests

"""Exercise full native reference and fault fields before target contract generation."""

from __future__ import annotations

import pytest
from amp_run_input import read_amp_run
from test_amp_image_flow import CONFIGURATION


@pytest.mark.parametrize("fault", ["drop", "delay", "freeze", "overload"])
def test_actual_native_fault_inputs(fault: str) -> None:
    """Admit original bounded fault schedules and real target workload selections.

    Parameters
    ----------
    fault
        Original native fault identifier.
    """
    overload = 100 if fault == "overload" else 0
    content = CONFIGURATION.replace(b"none 0 0 0 0", f"{fault} 3 1 {overload} 0".encode("ascii"))
    assert read_amp_run(content).overload_iterations == overload
    assert read_amp_run(content.replace(b"pid", b"lqr")).lqr == 1


@pytest.mark.parametrize(
    ("index", "replacement", "finding"),
    [
        (0, "other", "complete original"),
        (1, "1.0", "syntax"),
        (1, "-1", "outside bounds"),
        (14, "3", "outside bounds"),
        (18, "16", "outside bounds"),
        (19, "other", "fault kind"),
        (20, "1", "fault schedule"),
        (21, "1", "fault schedule"),
        (22, "1", "fault schedule"),
        (23, "1", "modeled latency"),
        (2, "0", "native integer"),
    ],
)
def test_invalid_complete_native_input(index: int, replacement: str, finding: str) -> None:
    """Refuse malformed complete native reference, mode and schedule fields.

    Parameters
    ----------
    index
        Original whitespace field index.
    replacement
        Invalid original field replacement.
    finding
        Required public refusal diagnostic.
    """
    words = CONFIGURATION.decode("ascii").split()
    words[index] = replacement
    with pytest.raises(ValueError, match=finding):
        read_amp_run(" ".join(words).encode("ascii"))


def test_original_encoding_and_schedule_refusals() -> None:
    """Refuse non-ASCII, incomplete inputs and fault cycles outside the actual run."""
    with pytest.raises(ValueError, match="ASCII"):
        read_amp_run(b"\xff")
    with pytest.raises(ValueError, match="complete original"):
        read_amp_run(CONFIGURATION + b" extra")
    with pytest.raises(ValueError, match="fault schedule"):
        read_amp_run(CONFIGURATION.replace(b"none 0 0 0 0", b"drop 10 1 0 0"))
    with pytest.raises(ValueError, match="fault schedule"):
        read_amp_run(CONFIGURATION.replace(b"none 0 0 0 0", b"drop 3 0 0 0"))
