# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — delay and jitter margins of the benchmark control loops

"""Delay and jitter margins of a benchmark loop, and the verdict on a measured latency range.

A loop samples its plant periodically and applies the command after an input-output delay
``Δ``. Theorem 1 of Cervin, Lincoln, Eker, Årzén and Buttazzo (2004), from Kao and Lincoln
(2004), guarantees stability for any time-varying ``Δ`` in ``[0, N*h]`` if, for every
``ω`` in ``(0, π]``::

    P_alias(ω) |K(e^{iω})| / |1 + P_ZOH(e^{iω}) K(e^{iω})| < 1 / (Ñ |e^{iω} - 1|)

with ``Ñ = sqrt(⌊N⌋² + 2⌊N⌋g + g)``, ``g = N - ⌊N⌋``, ``P_ZOH`` the zero-order-hold
discretization of the continuous plant ``P`` and ``P_alias(ω)² = Σ_k |P(i(ω+2πk)/h)|²``.
The condition is sufficient, so the jitter margin it gives is a lower bound. A state-feedback
loop is the scalar loop of ``K_state P(s)`` with ``K(z) = 1``.
"""

from __future__ import annotations

import cmath
from dataclasses import dataclass
from math import floor, isfinite, log10, pi, sin, sqrt
from typing import TYPE_CHECKING, Final

from loop_timing_witness.control_reference import MECHANICAL_STATES, Lqr, Pid, Plant

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

ALIAS_TERMS: Final = 64
"""Aliasing terms summed directly on each side; the leading-order tail is added exactly."""

GRID_POINTS: Final = 2000
"""Logarithmic frequency grid from ``1e-7`` to ``π`` rad per sample, before refinement."""


@dataclass(frozen=True)
class ContinuousPlant:
    """A benchmark plant in continuous time with its sample period.

    Attributes
    ----------
    numerator
        Coefficients of ``s`` from the constant term up for each state's response to the
        input: position and velocity for the mechanical model, temperature for the thermal model.
    denominator
        Characteristic polynomial from the constant term up.
    discrete
        Zero-order-hold discretization at ``period``.
    period
        Sample period in seconds.
    """

    numerator: tuple[tuple[float, ...], ...]
    denominator: tuple[float, ...]
    discrete: Plant
    period: float


@dataclass(frozen=True)
class Margins:
    """Timing margins of one loop.

    Attributes
    ----------
    crossover
        Gain crossover frequency in rad per sample, or ``None`` when the loop gain stays below
        one at every frequency.
    phase_margin
        Phase margin in radians at the crossover, or ``None`` without a crossover.
    delay_margin
        Constant delay margin ``phase_margin / crossover`` in sample periods, the
        continuous-time formula; ``None`` without a crossover.
    jitter_margin
        Largest ``N`` of Theorem 1 in sample periods: stability is guaranteed for any
        time-varying delay in ``[0, N*h]``.
    """

    crossover: float | None
    phase_margin: float | None
    delay_margin: float | None
    jitter_margin: float


def mechanical_continuous(
    plant: Plant, period: float, mass: float = 1.0, damping: float = 1.0, stiffness: float = 1.0
) -> ContinuousPlant:
    """Describe ``m*x'' + c*x' + k*x = u`` with its discretization.

    Parameters
    ----------
    plant
        Its zero-order-hold discretization at ``period``.
    period
        Sample period in seconds.
    mass, damping, stiffness
        Model parameters.

    Returns
    -------
    ContinuousPlant
        Position response ``1/(m s² + c s + k)`` and velocity response ``s/(m s² + c s + k)``.
    """
    return ContinuousPlant(((1.0,), (0.0, 1.0)), (stiffness, damping, mass), plant, period)


def thermal_continuous(
    plant: Plant, period: float, tau: float = 1.0, gain: float = 1.0
) -> ContinuousPlant:
    """Describe ``theta' = (-theta + gain*u)/tau`` with its discretization.

    Parameters
    ----------
    plant
        Its zero-order-hold discretization at ``period``.
    period
        Sample period in seconds.
    tau, gain
        Time constant and static gain.

    Returns
    -------
    ContinuousPlant
        Temperature response ``gain/(tau s + 1)``.
    """
    return ContinuousPlant(((gain,),), (1.0, tau), plant, period)


def _polynomial(coefficients: Sequence[float], value: complex) -> complex:
    """Evaluate a polynomial given from the constant term up.

    Parameters
    ----------
    coefficients
        Coefficients, constant term first.
    value
        Argument.

    Returns
    -------
    complex
        Polynomial value.
    """
    result = 0j
    for coefficient in reversed(coefficients):
        result = result * value + coefficient
    return result


def _loop(
    plant: ContinuousPlant, controller: Pid | Lqr
) -> tuple[
    Callable[[complex], complex], Callable[[complex], complex], Callable[[complex], complex]
]:
    """Return the scalar loop's continuous plant, discrete plant and controller responses.

    Parameters
    ----------
    plant
        Continuous plant with its discretization.
    controller
        PID acting on the first state, or state feedback.

    Returns
    -------
    tuple
        ``P(s)``, ``P_ZOH(z)`` and ``K(z)`` of the loop broken at the plant input.
    """
    weights = (
        (controller.kx, controller.kv)[: len(plant.numerator)]
        if isinstance(controller, Lqr)
        else (1.0, 0.0)[: len(plant.numerator)]
    )
    a, b = plant.discrete.transition, plant.discrete.input

    def continuous(s: complex) -> complex:
        denominator = _polynomial(plant.denominator, s)
        return sum(
            weight * _polynomial(numerator, s) / denominator
            for weight, numerator in zip(weights, plant.numerator, strict=True)
        )

    def discrete(z: complex) -> complex:
        if len(b) < MECHANICAL_STATES:
            return weights[0] * b[0] / (z - a[0][0])
        determinant = (z - a[0][0]) * (z - a[1][1]) - a[0][1] * a[1][0]
        position = ((z - a[1][1]) * b[0] + a[0][1] * b[1]) / determinant
        velocity = (a[1][0] * b[0] + (z - a[0][0]) * b[1]) / determinant
        return weights[0] * position + weights[1] * velocity

    def regulator(z: complex) -> complex:
        if isinstance(controller, Lqr):
            return 1.0 + 0j
        return (
            controller.kp
            + controller.ki_period * z / (z - 1)
            + controller.derivative_gain * (z - 1) / (z - controller.decay)
        )

    return continuous, discrete, regulator


def _alias(continuous: Callable[[complex], complex], omega: float, period: float) -> float:
    """Return ``P_alias(ω)`` with the leading-order tail of the sum added in closed form.

    Parameters
    ----------
    continuous
        Scalar continuous plant response.
    omega
        Frequency in rad per sample, in ``(0, π]``.
    period
        Sample period in seconds.

    Returns
    -------
    float
        Square root of the aliased power sum.
    """
    total = 0.0
    shifted = 0.0
    for k in range(-ALIAS_TERMS, ALIAS_TERMS + 1):
        total += abs(continuous(1j * (omega + 2 * pi * k) / period)) ** 2
        shifted += 1 / (omega + 2 * pi * k) ** 2
    # |P(iΩ)| ≈ c / Ω for a relative degree of one; c is read from a far frequency. For a
    # relative degree of two or more the tail is below 1e-12 of the sum and c is negligible.
    far = 1e9 / period
    coefficient = abs(continuous(1j * far)) * far * period
    tail = coefficient * coefficient * (1 / (4 * sin(omega / 2) ** 2) - shifted)
    return sqrt(total + tail)


def _stable(coefficients: Sequence[float]) -> bool:
    """Tell whether every root of a real polynomial lies strictly inside the unit circle.

    Parameters
    ----------
    coefficients
        Coefficients from the constant term up, leading coefficient non-zero.

    Returns
    -------
    bool
        Result of the Schur-Cohn reduction.
    """
    p = list(coefficients)
    while len(p) > 1:
        constant, leading = p[0], p[-1]
        if abs(constant) >= abs(leading):
            return False
        reversed_p = p[::-1]
        reduced = [leading * p[i] - constant * reversed_p[i] for i in range(len(p))]
        p = reduced[1:]
    return True


def _characteristic(plant: ContinuousPlant, controller: Pid | Lqr) -> list[float]:
    """Return the delay-free closed-loop characteristic polynomial, constant term first.

    Parameters
    ----------
    plant
        Continuous plant with its discretization.
    controller
        PID acting on the first state, or state feedback.

    Returns
    -------
    list[float]
        ``den_P den_K + num_P num_K`` of the loop broken at the plant input.
    """
    a, b = plant.discrete.transition, plant.discrete.input
    if len(b) < MECHANICAL_STATES:
        den_p = [-a[0][0], 1.0]
        weights = [controller.kx if isinstance(controller, Lqr) else 1.0]
        num_p = [weights[0] * b[0], 0.0]
    else:
        den_p = [a[0][0] * a[1][1] - a[0][1] * a[1][0], -(a[0][0] + a[1][1]), 1.0]
        kx, kv = (controller.kx, controller.kv) if isinstance(controller, Lqr) else (1.0, 0.0)
        position = [-a[1][1] * b[0] + a[0][1] * b[1], b[0]]
        velocity = [a[1][0] * b[0] - a[0][0] * b[1], b[1]]
        num_p = [kx * position[0] + kv * velocity[0], kx * position[1] + kv * velocity[1], 0.0]
    if isinstance(controller, Lqr):
        num_k, den_k = [1.0], [1.0]
    else:
        # K(z) = kp + ki z/(z-1) + g (z-1)/(z-d) over (z-1)(z-d).
        kp, ki, g, d = (
            controller.kp,
            controller.ki_period,
            controller.derivative_gain,
            controller.decay,
        )
        den_k = [d, -(1 + d), 1.0]
        num_k = [kp * d + g, -kp * (1 + d) - ki * d - 2 * g, kp + ki + g]
    product = _multiply(den_p, den_k)
    feedback = _multiply(num_p, num_k)
    size = max(len(product), len(feedback))
    padded = [*product, *[0.0] * (size - len(product))]
    return [padded[i] + (feedback[i] if i < len(feedback) else 0.0) for i in range(size)]


def _multiply(left: Sequence[float], right: Sequence[float]) -> list[float]:
    """Multiply two polynomials given from the constant term up.

    Parameters
    ----------
    left, right
        Factors.

    Returns
    -------
    list[float]
        Product.
    """
    product = [0.0] * (len(left) + len(right) - 1)
    for i, x in enumerate(left):
        for j, y in enumerate(right):
            product[i + j] += x * y
    return product


def margins(plant: ContinuousPlant, controller: Pid | Lqr) -> Margins:
    """Compute the crossover, phase, delay and jitter margins of a linear loop.

    Saturation, conditional integration and quantization are ignored: the margins describe
    the unsaturated linear loop around its operating point.

    Parameters
    ----------
    plant
        Continuous plant with its discretization.
    controller
        PID acting on the first state, or state feedback.

    Returns
    -------
    Margins
        Margins in rad per sample, radians and sample periods.

    Raises
    ------
    ValueError
        If the delay-free closed loop is not stable.
    """
    if not _stable(_characteristic(plant, controller)):
        message = "the delay-free closed loop is not stable"
        raise ValueError(message)
    continuous, discrete, regulator = _loop(plant, controller)
    grid = [1e-7 * (pi / 1e-7) ** (index / (GRID_POINTS - 1)) for index in range(GRID_POINTS)]
    gains = [abs(discrete(cmath.exp(1j * w)) * regulator(cmath.exp(1j * w))) for w in grid]
    crossover = phase = None
    for index in range(1, GRID_POINTS):
        if (gains[index - 1] - 1) * (gains[index] - 1) <= 0:
            low, high = grid[index - 1], grid[index]
            for _ in range(80):
                middle = sqrt(low * high)
                z = cmath.exp(1j * middle)
                if (abs(discrete(z) * regulator(z)) - 1) * (gains[index - 1] - 1) > 0:
                    low = middle
                else:
                    high = middle
            crossover = sqrt(low * high)
            z = cmath.exp(1j * crossover)
            phase = pi + cmath.phase(discrete(z) * regulator(z))
            break

    def bound(w: float) -> float:
        z = cmath.exp(1j * w)
        loop = discrete(z) * regulator(z)
        sensitivity = _alias(continuous, w, plant.period) * abs(regulator(z)) / abs(1 + loop)
        return 1 / (abs(z - 1) * sensitivity)

    values = [bound(w) for w in grid]
    worst = min(range(GRID_POINTS), key=values.__getitem__)
    low = grid[max(worst - 1, 0)]
    high = grid[min(worst + 1, GRID_POINTS - 1)]
    for _ in range(60):
        first = low * (high / low) ** (1 / 3)
        second = low * (high / low) ** (2 / 3)
        if bound(first) < bound(second):
            high = second
        else:
            low = first
    tilde = min(values[worst], bound(sqrt(low * high)))
    whole = floor(tilde)
    jitter = whole + (tilde * tilde - whole * whole) / (2 * whole + 1)
    return Margins(
        crossover,
        phase,
        None if crossover is None or phase is None else phase / crossover,
        jitter,
    )


def latency_verdict(
    margin: Margins, latencies: Sequence[float], period: float
) -> dict[str, object]:
    """Say whether measured input-output latencies lie inside a loop's jitter margin.

    Parameters
    ----------
    margin
        Margins of the loop.
    latencies
        Measured input-output delays in seconds, each from a sample to its applied command.
    period
        Sample period in seconds.

    Returns
    -------
    dict
        The largest latency in sample periods, the jitter margin and whether every latency
        lies inside it, so that any variation within the measured range keeps the linear loop
        stable.

    Raises
    ------
    ValueError
        If there are no latencies, a latency is negative or not finite, or the period is not
        positive.
    """
    if not latencies or period <= 0 or any(not isfinite(x) or x < 0 for x in latencies):
        message = "a verdict needs finite, non-negative latencies and a positive period"
        raise ValueError(message)
    largest = max(latencies) / period
    return {
        "largest_latency_periods": largest,
        "jitter_margin_periods": margin.jitter_margin,
        "within_jitter_margin": largest < margin.jitter_margin,
        "log10_headroom": log10(margin.jitter_margin / largest) if largest > 0 else None,
    }
