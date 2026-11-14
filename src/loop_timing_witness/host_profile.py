# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — run limits derived from the executing host's profile

"""Derive hang guards and build parallelism from the host that carries the work.

Hang guards in the tests and tools are written for the reference profile: the
development hosts and hosted runners the project runs on today, which all have
the timeout scale 1. Another host declares its own scale in the environment
variable ``WITNESS_HOST_TIMEOUT_SCALE``, and every hang guard is multiplied by
it. Build parallelism is the number of processors this process may run on.
Explicit policy limits, such as the hosted workflows' job timeouts and the
neural checker's resource limits, are reviewed values and are not derived here.
"""

from __future__ import annotations

import math
import os
from typing import Final

SCALE_VARIABLE: Final = "WITNESS_HOST_TIMEOUT_SCALE"
DECIMAL_CHARACTERS: Final = frozenset("0123456789.eE+-")


def timeout_scale() -> float:
    """Return the executing host's timeout scale.

    The declaration is a plain decimal number: digits, an optional sign, point
    and exponent, without spaces, digit separators or non-ASCII digits, so that
    every reader of the variable admits the same declarations.

    Returns
    -------
    float
        The declared positive finite scale, or 1 for the reference profile when
        none is declared.

    Raises
    ------
    ValueError
        If the declared scale is not a positive finite number.
    """
    text = os.environ.get(SCALE_VARIABLE)
    if text is None:
        return 1.0
    try:
        scale = float(text) if set(text) <= DECIMAL_CHARACTERS else math.nan
    except ValueError:
        scale = math.nan
    if not math.isfinite(scale) or scale <= 0:
        message = f"{SCALE_VARIABLE} must be a positive finite number"
        raise ValueError(message)
    return scale


def scaled(seconds: float) -> float:
    """Return one hang guard for the executing host.

    Parameters
    ----------
    seconds
        The guard on the reference profile.

    Returns
    -------
    float
        The guard multiplied by the host's timeout scale.

    Raises
    ------
    ValueError
        If the declared scale is not a positive finite number.
    """
    return seconds * timeout_scale()


def scaled_seconds(seconds: int) -> int:
    """Return one whole-second hang guard for the executing host.

    Parameters
    ----------
    seconds
        The guard on the reference profile, in whole seconds.

    Returns
    -------
    int
        The scaled guard rounded up to whole seconds, for interfaces that take
        whole seconds.

    Raises
    ------
    ValueError
        If the declared scale is not a positive finite number.
    """
    return math.ceil(scaled(seconds))


def build_jobs() -> int:
    """Return the build parallelism of the executing host.

    Returns
    -------
    int
        The processors this process may run on, at least one.
    """
    return os.process_cpu_count() or 1
