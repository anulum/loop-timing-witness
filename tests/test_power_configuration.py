# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real native power configuration refusals

"""Validate explicit power acquisition contracts through the native UIO CLI."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration
from test_native_uio_run import native_uio

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_uio"]


@pytest.mark.parametrize(
    ("index", "replacement", "error"),
    [
        (0, "unknown-v1", "invalid power ABI"),
        (1, "../../device", "invalid power ABI"),
        (2, "bad/kernel", "invalid power ABI"),
        (3, "49999999", "integer outside range"),
        (4, "60000001", "integer outside range"),
        (5, "-1", "integer outside range"),
        (6, "128", "unsupported PAC1934 sample rate"),
        (7, "VDDA", "power rails must"),
        (8, "5", "integer outside range"),
        (9, "0", "integer outside range"),
        (10, "label,comma", "invalid power label"),
        (12, "1", "duplicate channel"),
        (22, "extra", "extra or unreadable"),
        (3, "60000000001", "integer outside range"),
        (3, "18446744073709551616", "integer outside range"),
        (3, "60000000suffix", "integer outside range"),
        (3, "+60000000", "integer outside range"),
        (3, "60000000\x00", "integer outside range"),
        (5, "2147483648", "integer outside range"),
        (8, "0", "integer outside range"),
        *[
            (
                23,
                str(length),
                "invalid power ABI"
                if length < 3
                else "incomplete power configuration"
                if length < 7 or length % 4 in {0, 1}
                else "power rails must"
                if length % 4 == 3
                else "invalid power label",
            )
            for length in range(23)
        ],
    ],
)
def test_refused_power_configuration(
    native_uio: Path, tmp_path: Path, index: int, replacement: str, error: str
) -> None:
    """Refuse malformed configuration before opening hardware or writing output.

    Parameters
    ----------
    native_uio
        Actual native UIO executable.
    tmp_path
        Exclusive case directory.
    index
        Token to replace, 22 to append, or 23 to truncate the configuration.
    replacement
        Invalid public value or retained token count for a truncated file.
    error
        Expected acquisition refusal.
    """
    tokens = [
        "pac1934-iio-mchp-v1",
        "iio:device4294967295",
        os.uname().release,
        "60000000",
        "50000000",
        str(min(os.sched_getaffinity(0))),
        "1024",
        "VDD",
        "1",
        "10000",
        "rail1",
        "VDD25",
        "2",
        "10000",
        "rail2",
        "VDDA25",
        "3",
        "10000",
        "rail3",
        "VDDA",
        "4",
        "10000",
        "rail4",
    ]
    if index == 22:
        tokens.append(replacement)
    elif index == 23:
        tokens = tokens[: int(replacement)]
    else:
        tokens[index] = replacement
    power = tmp_path / "power.conf"
    power.write_text(" ".join(tokens), encoding="utf-8")
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw, journal = (tmp_path / name for name in ("events.bin", "raw.csv", "power.csv"))
    result = subprocess.run(
        [
            str(native_uio),
            str(config),
            str(events),
            str(raw),
            "uio4294967295",
            "witness",
            "devicetree",
            "0",
            "0",
            "--metadata",
            str(tmp_path / "metadata.json"),
            "--power-config",
            str(power),
            "--power-journal",
            str(journal),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert error in result.stderr
    assert not any(path.exists() for path in (events, raw, journal))
    assert not (tmp_path / "metadata.json").exists()
