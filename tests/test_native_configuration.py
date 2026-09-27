# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native complete configuration refusal boundaries

"""Refuse complete invalid run contracts before acquiring output or starting RTL."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


@pytest.mark.parametrize(
    ("index", "value", "error"),
    [
        (1, "0", "invalid cycles, period or controller coefficients"),
        (2, "0", "invalid cycles, period or controller coefficients"),
        (3, "-1", "invalid cycles, period or controller coefficients"),
        (14, "3", "configuration integer outside range"),
        (15, "2147483648", "configuration integer outside range"),
        (15, "-2147483649", "configuration integer outside range"),
        (18, "16", "configuration integer outside range"),
        (19, "unknown", "unknown fault kind"),
        (20, "1", "invalid fault schedule or overload configuration"),
        (21, "1", "invalid fault schedule or overload configuration"),
        (22, "1", "invalid fault schedule or overload configuration"),
        (23, "1", "invalid fault schedule or overload configuration"),
        (22, "10000001", "configuration integer outside range"),
        (23, "10000001", "configuration integer outside range"),
        (1, "+", "invalid configuration integer"),
        (1, "-", "invalid configuration integer"),
        (1, "32tail", "invalid configuration integer"),
    ],
)
def test_complete_configuration_refusal(
    native_run: Path, tmp_path: Path, index: int, value: str, error: str
) -> None:
    """Check each invalid complete contract through the actual production CLI.

    Parameters
    ----------
    native_run
        Executable linked to the actual production RTL plant.
    tmp_path
        Exclusive configuration and output allocation.
    index
        Whitespace-delimited public configuration field to replace.
    value
        Invalid field value within an otherwise complete valid configuration.
    error
        Specific semantic refusal required from the actual parser.
    """
    fields = configuration("pid", "none").split()
    fields[index] = value
    assert_refusal(native_run, tmp_path, " ".join(fields), error)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        (configuration("pid", "none") + "extra", "extra or unreadable run configuration"),
        (
            configuration("pid", "drop").replace("drop 0 1", "drop 32 1"),
            "invalid fault schedule or overload configuration",
        ),
        (
            configuration("pid", "drop").replace("drop 0 1", "drop 0 0"),
            "invalid fault schedule or overload configuration",
        ),
    ],
)
def test_configuration_schedule_and_trailing_refusal(
    native_run: Path, tmp_path: Path, text: str, error: str
) -> None:
    """Reject out-of-run faults, empty injections and trailing configuration fields.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Exclusive input and output allocation.
    text
        Complete invalid configuration submitted without metadata pre-hashing.
    error
        Expected production parser error.
    """
    assert_refusal(native_run, tmp_path, text, error)


def assert_refusal(native_run: Path, tmp_path: Path, text: str, error: str) -> None:
    """Verify the public error and absence of all run evidence after parser refusal.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Exclusive input and output allocation.
    text
        Configuration content to submit unchanged.
    error
        Expected precise parser refusal.
    """
    config = tmp_path / "run.conf"
    config.write_text(text, encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "tracking.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == error
    assert not events.exists()
    assert not raw.exists()


def test_absent_configuration_without_metadata(native_run: Path, tmp_path: Path) -> None:
    """Reach the configuration-open refusal before outputs without a digest option.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Exclusive nonexistent input and output allocation.
    """
    result = subprocess.run(
        [
            str(native_run),
            str(tmp_path / "absent.conf"),
            str(tmp_path / "events.bin"),
            str(tmp_path / "tracking.csv"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "cannot open run configuration"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("options", "error"),
    [
        (
            ["--power-config", "absent.conf"],
            "power configuration and journal must be supplied together",
        ),
        (
            ["--power-journal", "power.csv"],
            "power configuration and journal must be supplied together",
        ),
        (
            ["--power-config", "absent.conf", "--power-journal", "power.csv"],
            "power acquisition requires native metadata",
        ),
    ],
)
def test_simulation_power_contract_refusal(
    native_run: Path, tmp_path: Path, options: list[str], error: str
) -> None:
    """Reject incomplete acquisition options before reading files or creating output.

    Parameters
    ----------
    native_run
        Actual simulation entry point sharing the production option parser.
    tmp_path
        Empty exclusive allocation for every input and output name.
    options
        Incomplete physical acquisition arguments sent unchanged to the CLI.
    error
        Required shared option parser error before the simulation transport guard.
    """
    result = subprocess.run(
        [
            str(native_run),
            str(tmp_path / "absent.conf"),
            str(tmp_path / "events.bin"),
            str(tmp_path / "tracking.csv"),
            *options,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == error
    assert not list(tmp_path.iterdir())
