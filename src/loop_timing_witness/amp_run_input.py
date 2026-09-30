# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original native run configuration admission for target firmware

"""Read complete original native run inputs before compiling dedicated-hart firmware."""

from __future__ import annotations

import re

from .amp_contract import INT32_MAX, INT32_MIN, UINT32_MAX, AmpRun

TOKEN_COUNT = 24
COEFFICIENT_START = 3
COEFFICIENT_END = 14
FAULT_INDEX = 19
MAX_REFERENCE_MODE = 2
MAX_PHASE = 15


def _integer(token: str, minimum: int, maximum: int) -> int:
    """Require original native whole decimal syntax and explicit field bounds.

    Parameters
    ----------
    token
        Original whitespace-delimited field.
    minimum
        Inclusive lower bound.
    maximum
        Inclusive upper bound.

    Returns
    -------
    int
        Validated original integer.

    Raises
    ------
    ValueError
        If syntax or bounds violate the native parser contract.
    """
    if re.fullmatch(r"[+-]?[0-9]+", token) is None:
        message = "AMP native configuration integer syntax is invalid"
        raise ValueError(message)
    value = int(token)
    if not minimum <= value <= maximum:
        message = "AMP native configuration integer is outside bounds"
        raise ValueError(message)
    return value


def read_amp_run(content: bytes) -> AmpRun:
    """Validate all native fields and require actual target work without modeled latency.

    Parameters
    ----------
    content
        Complete original native whitespace configuration retained for the fabric and firmware.

    Returns
    -------
    AmpRun
        Immutable target controller/run fields from the same complete configuration.

    Raises
    ------
    ValueError
        If original encoding, fields, reference/fault schedule or native invariants are invalid.
    """
    try:
        tokens = content.decode("ascii").split()
    except UnicodeDecodeError as error:
        message = "AMP native configuration must be ASCII"
        raise ValueError(message) from error
    if len(tokens) != TOKEN_COUNT or tokens[0] not in ("pid", "lqr"):
        message = "AMP requires the complete original native run configuration"
        raise ValueError(message)
    cycles = _integer(tokens[1], 0, UINT32_MAX)
    period = _integer(tokens[2], 0, UINT32_MAX)
    coefficients = tuple(
        _integer(word, INT32_MIN, INT32_MAX) for word in tokens[COEFFICIENT_START:COEFFICIENT_END]
    )
    _integer(tokens[14], 0, MAX_REFERENCE_MODE)
    for word in tokens[15:18]:
        _integer(word, INT32_MIN, INT32_MAX)
    _integer(tokens[18], 0, MAX_PHASE)
    fault = tokens[FAULT_INDEX]
    if fault not in ("none", "drop", "delay", "freeze", "overload"):
        message = "AMP native fault kind is invalid"
        raise ValueError(message)
    fault_cycle, fault_periods, overload, modeled_ns = (
        _integer(word, 0, UINT32_MAX) for word in tokens[20:24]
    )
    if (
        (fault == "none" and (fault_cycle or fault_periods))
        or (fault != "none" and (fault_cycle >= cycles or not fault_periods))
        or (fault != "overload" and overload)
        or modeled_ns
    ):
        message = "AMP native fault schedule or modeled latency is invalid"
        raise ValueError(message)
    return AmpRun(cycles, period, int(tokens[0] == "lqr"), overload, coefficients)
