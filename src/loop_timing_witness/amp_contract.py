# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable native firmware run and platform contract generation

"""Render typed immutable C resources with actual compiler-enforced mailbox capacity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .amp_platform import AmpPlatform

UINT32_MAX = (1 << 32) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
SCALE = 1 << 24
COEFFICIENT_COUNT = 11
MAX_OVERLOAD_ITERATIONS = 10000000
MAX_DURATION_TICKS = (((1 << 64) - 1) - 1000000000) // 10


@dataclass(frozen=True)
class AmpRun:
    """Explicit immutable native controller inputs compiled into one firmware image.

    Parameters
    ----------
    cycles
        Positive complete run cycle count.
    period_ticks
        Positive original fabric period in 10 ns ticks.
    lqr
        Integer controller selector, zero for PID or one for LQR.
    overload_iterations
        Actual target instruction workload count, without modeled latency substitution.
    coefficients
        Eleven original signed raw Q8.24 words in witness_coefficients declaration order.
    """

    cycles: int
    period_ticks: int
    lqr: int
    overload_iterations: int
    coefficients: tuple[int, ...]

    def __post_init__(self) -> None:
        """Refuse invalid scalar bounds and the original native coefficient invariants.

        Raises
        ------
        ValueError
            If any input differs from the exact native integer and coefficient contract.
        """
        values = (self.cycles, self.period_ticks, self.lqr, self.overload_iterations)
        if (
            any(type(value) is not int or not 0 <= value <= UINT32_MAX for value in values)
            or not self.cycles
            or not self.period_ticks
            or self.lqr not in (0, 1)
            or self.overload_iterations > MAX_OVERLOAD_ITERATIONS
            or self.cycles * self.period_ticks > MAX_DURATION_TICKS
            or type(self.coefficients) is not tuple
            or len(self.coefficients) != COEFFICIENT_COUNT
            or any(
                type(value) is not int or not INT32_MIN <= value <= INT32_MAX
                for value in self.coefficients
            )
        ):
            message = "AMP run inputs violate the native integer contract"
            raise ValueError(message)
        kp, ki, decay, derivative, _, _, _, lower, upper, integral_lower, integral_upper = (
            self.coefficients
        )
        if (
            not lower <= 0 <= upper
            or not integral_lower <= 0 <= integral_upper
            or kp < 0
            or ki < 0
            or derivative < 0
            or not 0 <= decay <= SCALE
        ):
            message = "AMP run coefficients violate the native controller invariants"
            raise ValueError(message)


def render_contract(platform: AmpPlatform, run: AmpRun) -> str:
    """Render immutable native data and require the actual C mailbox to fit reserved memory.

    Parameters
    ----------
    platform
        Complete original resources returned by platform admission.
    run
        Validated native raw controller inputs.

    Returns
    -------
    str
        Complete freestanding C translation unit for the original firmware ABI.
    """
    device = platform.device
    addresses = (
        device.aperture.address,
        device.plic.priority,
        device.plic.enable_word,
        device.plic.threshold,
        device.plic.claim,
        platform.memory.shared.address,
    )
    resources = ", ".join(f"UINT64_C({value})" for value in addresses)
    inputs = ", ".join(
        f"UINT32_C({value})"
        for value in (run.cycles, run.period_ticks, run.lqr, run.overload_iterations)
    )
    coefficients = ", ".join(
        "INT32_MIN" if value == INT32_MIN else f"INT32_C({value})" for value in run.coefficients
    )
    return f"""// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — generated immutable firmware resource and run contract
#include "runtime/bare_metal/amp_contract.h"
_Static_assert(sizeof(witness_amp_mailbox) <= UINT64_C({platform.memory.shared.size}),
               "actual telemetry ABI exceeds reserved memory");
const witness_amp_platform_contract witness_amp_platform = {{
    UINT32_C({platform.hart}), UINT32_C({platform.source}), {resources}
}};
const witness_amp_run_contract witness_amp_run = {{
    {inputs}, {{{coefficients}}}
}};
"""
