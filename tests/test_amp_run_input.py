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


@pytest.mark.parametrize("separator", [b"\t", b"\n", b"\x0b", b"\x0c", b"\r\n"])
def test_native_whitespace_separates_fields(separator: bytes) -> None:
    """Admit the C locale's whitespace between fields, as the native reader does.

    Parameters
    ----------
    separator
        Whitespace the native stream reader skips.
    """
    assert read_amp_run(separator.join(CONFIGURATION.split())) == read_amp_run(CONFIGURATION)


@pytest.mark.parametrize("separator", [b"\x1c", b"\x1d", b"\x1e", b"\x1f"])
def test_information_separators_stay_inside_fields(separator: bytes) -> None:
    """Refuse the ASCII information separators the native reader keeps inside a field.

    Parameters
    ----------
    separator
        ASCII information separator that Python's text splitting would skip.
    """
    words = CONFIGURATION.split()
    joined = b" ".join([words[0] + separator + words[1], *words[2:]])
    with pytest.raises(ValueError, match="complete original native run configuration"):
        read_amp_run(joined)
    with pytest.raises(ValueError, match="integer syntax is invalid"):
        read_amp_run(CONFIGURATION.rstrip() + separator)


def test_native_digits_and_magnitudes() -> None:
    """Admit leading zeros at any length and refuse magnitudes beyond every bound."""
    words = CONFIGURATION.decode("ascii").split()
    padded = list(words)
    padded[1] = "+" + "0" * 5000 + words[1]
    padded[15] = "-" + "0" * 5000 + "1"
    assert read_amp_run(" ".join(padded).encode("ascii")) == read_amp_run(CONFIGURATION)
    widest = list(words)
    widest[1] = "4294967295"
    widest[7] = "-2147483648"
    run = read_amp_run(" ".join(widest).encode("ascii"))
    assert (run.cycles, run.coefficients[4]) == (4294967295, -2147483648)
    for index, token in [(1, "9" * 5000), (1, "10000000000"), (7, "-2147483649")]:
        refused = list(words)
        refused[index] = token
        with pytest.raises(
            ValueError, match=r"^AMP native configuration integer is outside bounds$"
        ):
            read_amp_run(" ".join(refused).encode("ascii"))
