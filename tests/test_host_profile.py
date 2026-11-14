# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host-profile limits

"""Derive hang guards and build parallelism from the executing host's profile."""

from __future__ import annotations

import os

import pytest

from loop_timing_witness.host_profile import (
    SCALE_VARIABLE,
    build_jobs,
    scaled,
    scaled_seconds,
    timeout_scale,
)


def test_reference_profile_keeps_every_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the written guard on a host that declares no scale.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    """
    monkeypatch.delenv(SCALE_VARIABLE, raising=False)
    assert timeout_scale() == 1.0
    assert scaled(30) == 30
    assert scaled_seconds(30) == 30


@pytest.mark.parametrize(
    ("text", "scale", "whole"),
    [
        ("2", 2.0, 20),
        ("0.5", 0.5, 5),
        ("0.25", 0.25, 3),
        ("1e-3", 0.001, 1),
        ("+2.", 2.0, 20),
        (".5E+1", 5.0, 50),
    ],
)
def test_declared_scale_multiplies_every_guard(
    monkeypatch: pytest.MonkeyPatch, text: str, scale: float, whole: int
) -> None:
    """Multiply each guard by the host's declared scale, whole seconds rounded up.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    text
        Declared scale.
    scale
        Its value.
    whole
        The ten-second guard in whole seconds.
    """
    monkeypatch.setenv(SCALE_VARIABLE, text)
    assert timeout_scale() == scale
    assert scaled(10) == 10 * scale
    assert scaled_seconds(10) == whole


@pytest.mark.parametrize(
    "text",
    [
        "0",
        "-1",
        "1e-400",
        "nan",
        "inf",
        "1e400",
        "",
        "two",
        " 2",
        "2\n",
        "1_0",
        chr(0x661),
        "1e",
        ".",
    ],
)
def test_invalid_scale_is_refused(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Refuse a declared scale that is not a positive finite plain decimal number.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    text
        Declared scale.
    """
    monkeypatch.setenv(SCALE_VARIABLE, text)
    with pytest.raises(ValueError, match=f"^{SCALE_VARIABLE} must be a positive finite number$"):
        scaled(1)


def test_build_jobs_follow_the_usable_processors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build with every processor this process may run on, and at least one.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    """
    assert build_jobs() == len(os.sched_getaffinity(0))
    monkeypatch.setattr(os, "process_cpu_count", lambda: None)
    assert build_jobs() == 1
