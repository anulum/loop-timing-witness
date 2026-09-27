# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual Linux host load request validation

"""Validate the public load request before any scheduling or resource mutation."""

from __future__ import annotations

import os

import pytest
from linux_load_config import PROFILES, LoadConfiguration


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("size", [4096, 60000])
def test_valid_request(profile: str, size: int) -> None:
    """Accept bounded requests using a CPU actually allowed by the kernel.

    Parameters
    ----------
    profile
        Supported actual worker profile.
    size
        Valid lower bound or UDP maximum.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    request = LoadConfiguration(profile, min(affinity), size)
    request.validate()
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler


@pytest.mark.parametrize(
    ("profile", "size", "message"),
    [
        ("unknown", 4096, "unsupported"),
        ("memory", 4095, "working set"),
        ("memory", 16777217, "working set"),
        ("network", 60001, "datagram"),
    ],
)
def test_invalid_request(profile: str, size: int, message: str) -> None:
    """Refuse profile and buffer violations without changing parent scheduling.

    Parameters
    ----------
    profile
        Requested profile name.
    size
        Out-of-contract buffer size where applicable.
    message
        Specific refusal expected from the public validator.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    with pytest.raises(ValueError, match=message):
        LoadConfiguration(profile, min(affinity), size).validate()
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler


def test_cpu_outside_affinity() -> None:
    """Refuse a genuinely disallowed CPU before changing the actual parent mask."""
    affinity = os.sched_getaffinity(0)
    with pytest.raises(ValueError, match="outside inherited affinity"):
        LoadConfiguration("cpu", max(affinity) + 1).validate()
    assert os.sched_getaffinity(0) == affinity


def test_memory_upper_bound() -> None:
    """Accept the exact memory resource maximum without allocating a buffer."""
    LoadConfiguration("memory", min(os.sched_getaffinity(0)), 16777216).validate()
