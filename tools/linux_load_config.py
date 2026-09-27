# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — explicit bounded Linux load configuration

"""Validate host load requests before allocating processes or working files."""

from __future__ import annotations

import os
from dataclasses import dataclass

MIN_WORKING_SET_BYTES = 4096
MAX_WORKING_SET_BYTES = 16 * 1024 * 1024
MAX_DATAGRAM_BYTES = 60000

PROFILES = ("idle", "cpu", "memory", "network", "storage")


@dataclass(frozen=True)
class LoadConfiguration:
    """One normal-policy worker on an explicitly allowed CPU.

    Parameters
    ----------
    profile
        Idle wait, CPU arithmetic, memory/cache, loopback UDP or owned-file storage.
    cpu
        CPU selected from the launching process's inherited affinity.
    working_set_bytes
        Buffer/file limit; CPU arithmetic and idle do not allocate this buffer.
    """

    profile: str
    cpu: int
    working_set_bytes: int = MIN_WORKING_SET_BYTES

    def validate(self) -> None:
        """Refuse invalid profiles, affinity requests and resource bounds.

        Raises
        ------
        ValueError
            If a request cannot be honoured within the explicit host resource contract.
        """
        if self.profile not in PROFILES:
            message = "unsupported Linux load profile"
            raise ValueError(message)
        if self.cpu not in os.sched_getaffinity(0):
            message = "load CPU is outside inherited affinity"
            raise ValueError(message)
        if not MIN_WORKING_SET_BYTES <= self.working_set_bytes <= MAX_WORKING_SET_BYTES:
            message = "load working set must be between 4096 and 16777216 bytes"
            raise ValueError(message)
        if self.profile == "network" and self.working_set_bytes > MAX_DATAGRAM_BYTES:
            message = "loopback UDP load requires at most 60000 bytes per datagram"
            raise ValueError(message)
