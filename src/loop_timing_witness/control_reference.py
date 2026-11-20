# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — float64 reference of the benchmark control loops

"""Float64 reference of the benchmark plants and controllers, and fixed-point loop checks.

The fixed-point controllers and the emulated plants use signed Q8.24 integers with floor
division. This module computes the same closed loops in float64 from the unquantized design
values, so the difference between the two measures what quantization changes. It also finds
the steady-state period of a recorded fixed-point trajectory, which detects a limit cycle
exactly: the recorded tuple is the loop's complete state, so a repeated tuple repeats for ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, exp, sin, sqrt
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

SCALE: Final = 1 << 24
"""Raw Q8.24 units per real unit."""

_DERIVATIVE_LIMIT: Final = float((1 << 31) - 1) / SCALE
"""Largest derivative state the fixed-point PID holds, in real units."""

MECHANICAL_STATES: Final = 2
"""States of the mechanical model: position and velocity."""


@dataclass(frozen=True)
class Plant:
    """Zero-order-hold discretization of a benchmark plant in real units.

    Attributes
    ----------
    transition
        State transition matrix: two by two for the mechanical model, one by one for the
        thermal model.
    input
        Input vector with one entry per state.
    """

    transition: tuple[tuple[float, ...], ...]
    input: tuple[float, ...]


@dataclass(frozen=True)
class Pid:
    """PID with filtered derivative on measurement and conditional integration.

    Attributes
    ----------
    kp, ki_period, decay, derivative_gain
        Proportional gain, ``Ki*T``, ``Tf/(Tf+T)`` and ``Kd/(Tf+T)``.
    output_min, output_max, integral_min, integral_max
        Actuator and integral bounds.
    """

    kp: float
    ki_period: float
    decay: float
    derivative_gain: float
    output_min: float
    output_max: float
    integral_min: float
    integral_max: float


@dataclass(frozen=True)
class Lqr:
    """Discrete state feedback ``u = nr*r - kx*x - kv*v`` with actuator bounds.

    Attributes
    ----------
    kx, kv, nr
        Position, velocity and reference gains.
    output_min, output_max
        Actuator bounds.
    """

    kx: float
    kv: float
    nr: float
    output_min: float
    output_max: float


@dataclass(frozen=True)
class Sample:
    """One sample of a closed loop in real units.

    Attributes
    ----------
    output, velocity
        Plant output and, for the mechanical model, velocity (zero for the thermal model).
    command
        Controller command computed from this sample.
    """

    output: float
    velocity: float
    command: float


def mechanical_plant(
    period: float = 0.001, mass: float = 1.0, damping: float = 1.0, stiffness: float = 1.0
) -> Plant:
    """Discretize ``m*x'' + c*x' + k*x = u`` with a zero-order hold.

    Parameters
    ----------
    period
        Sample period in seconds.
    mass, damping, stiffness
        Underdamped model parameters, ``c**2 < 4*k*m``.

    Returns
    -------
    Plant
        Exact discretization of the normalized model.

    Raises
    ------
    ValueError
        If a parameter is not positive or the model is not underdamped.
    """
    if min(period, mass, damping, stiffness) <= 0 or damping * damping >= 4 * stiffness * mass:
        message = "mechanical plant needs positive, underdamped parameters"
        raise ValueError(message)
    alpha = damping / (2 * mass)
    beta = sqrt(stiffness / mass - alpha * alpha)
    decay = exp(-alpha * period)
    c = decay * cos(beta * period)
    s = decay * sin(beta * period) / beta
    omega2 = stiffness / mass
    return Plant(
        ((c + alpha * s, s), (-omega2 * s, c - alpha * s)),
        ((1 - c - alpha * s) / stiffness, s / mass),
    )


def thermal_plant(period: float = 0.001, tau: float = 1.0, gain: float = 1.0) -> Plant:
    """Discretize ``theta' = (-theta + gain*u)/tau`` with a zero-order hold.

    Parameters
    ----------
    period
        Sample period in seconds.
    tau, gain
        Time constant and static gain.

    Returns
    -------
    Plant
        Exact discretization of the first-order model.

    Raises
    ------
    ValueError
        If a parameter is not positive.
    """
    if min(period, tau, gain) <= 0:
        message = "thermal plant needs positive parameters"
        raise ValueError(message)
    pole = exp(-period / tau)
    return Plant(((pole,),), (gain * (1 - pole),))


def default_pid() -> Pid:
    """Return the documented emulator PID before quantization.

    Returns
    -------
    Pid
        ``Kp=2``, ``Ki=1``, ``Kd=0.0005``, ``Tf=T=0.001``, output ±4 and integral ±2.
    """
    period = filter_time = 0.001
    return Pid(
        kp=2.0,
        ki_period=1.0 * period,
        decay=filter_time / (filter_time + period),
        derivative_gain=0.0005 / (filter_time + period),
        output_min=-4.0,
        output_max=4.0,
        integral_min=-2.0,
        integral_max=2.0,
    )


def lqr(plant: Plant, state_weights: Sequence[float], input_weight: float = 1.0) -> Lqr:
    """Solve the discrete Riccati recurrence from ``P=Q`` and add reference scaling.

    Parameters
    ----------
    plant
        Discretized plant.
    state_weights
        Diagonal of ``Q``, one entry per state.
    input_weight
        ``R``.

    Returns
    -------
    Lqr
        Gains with output bounds ±4; ``kv`` is zero for the thermal model.

    Raises
    ------
    ValueError
        If the weights do not match the plant or the recurrence does not converge.
    """
    size = len(plant.input)
    if len(state_weights) != size or min(*state_weights, input_weight) <= 0:
        message = "LQR needs one positive weight per state and a positive input weight"
        raise ValueError(message)
    a, b = plant.transition, plant.input
    q = [[state_weights[i] if i == j else 0.0 for j in range(size)] for i in range(size)]
    p = [row[:] for row in q]
    for _ in range(100_000):
        pb = [sum(p[i][j] * b[j] for j in range(size)) for i in range(size)]
        pa = [
            [sum(p[i][k] * a[k][j] for k in range(size)) for j in range(size)] for i in range(size)
        ]
        denominator = input_weight + sum(b[i] * pb[i] for i in range(size))
        gains = [sum(b[i] * pa[i][j] for i in range(size)) / denominator for j in range(size)]
        following = [
            [
                q[i][j]
                + sum(a[h][i] * pa[h][j] for h in range(size))
                - sum(a[h][i] * pb[h] for h in range(size)) * gains[j]
                for j in range(size)
            ]
            for i in range(size)
        ]
        residual = max(abs(following[i][j] - p[i][j]) for i in range(size) for j in range(size))
        p = following
        if residual < 1e-12 * max(1.0, *(abs(value) for row in p for value in row)):
            closed = [[a[i][j] - b[i] * gains[j] for j in range(size)] for i in range(size)]
            return Lqr(
                gains[0],
                gains[1] if size == MECHANICAL_STATES else 0.0,
                _reference_gain(closed, b),
                -4.0,
                4.0,
            )
    message = "discrete Riccati recurrence did not converge"
    raise ValueError(message)


def _reference_gain(closed: list[list[float]], b: tuple[float, ...]) -> float:
    """Return the gain that gives unit steady-state output for a unit reference.

    Parameters
    ----------
    closed
        Closed-loop matrix ``A-BK``.
    b
        Input vector.

    Returns
    -------
    float
        ``1 / ([1, 0] (I-F)^-1 B)``, or ``(1-F)/B`` for one state.
    """
    if len(b) == 1:
        return (1 - closed[0][0]) / b[0]
    m00, m01 = 1 - closed[0][0], -closed[0][1]
    m10, m11 = -closed[1][0], 1 - closed[1][1]
    determinant = m00 * m11 - m01 * m10
    return determinant / (m11 * b[0] - m01 * b[1])


def _clamp(value: float, low: float, high: float) -> float:
    """Return a value limited to a closed interval.

    Parameters
    ----------
    value, low, high
        Value and bounds.

    Returns
    -------
    float
        The nearest value in ``[low, high]``.
    """
    return min(max(value, low), high)


def closed_loop(
    plant: Plant, controller: Pid | Lqr, reference: float, samples: int
) -> list[Sample]:
    """Run a closed loop in float64 with the fixed-point loop's timing.

    The plant starts at rest with a zero actuator. At sample ``k`` the plant state becomes
    ``A x + B u`` with the command of sample ``k-1``, the controller reads that output and
    computes the command the plant uses at sample ``k+1``.

    Parameters
    ----------
    plant
        Discretized plant.
    controller
        PID or LQR in real units.
    reference
        Constant reference.
    samples
        Number of samples, at least one.

    Returns
    -------
    list[Sample]
        One entry per sample.

    Raises
    ------
    ValueError
        If ``samples`` is not positive.
    """
    if samples <= 0:
        message = "a closed loop needs at least one sample"
        raise ValueError(message)
    size = len(plant.input)
    state = [0.0] * size
    command = integral = derivative = previous = 0.0
    trajectory = []
    for index in range(samples):
        state = [
            sum(plant.transition[i][j] * state[j] for j in range(size)) + plant.input[i] * command
            for i in range(size)
        ]
        output = state[0]
        velocity = state[1] if size == MECHANICAL_STATES else 0.0
        if isinstance(controller, Lqr):
            command = _clamp(
                controller.nr * reference - controller.kx * output - controller.kv * velocity,
                controller.output_min,
                controller.output_max,
            )
        else:
            error = reference - output
            derivative = (
                0.0
                if index == 0
                else _clamp(
                    controller.decay * derivative
                    - controller.derivative_gain * (output - previous),
                    -_DERIVATIVE_LIMIT,
                    _DERIVATIVE_LIMIT,
                )
            )
            proposed = _clamp(
                integral + controller.ki_period * error,
                controller.integral_min,
                controller.integral_max,
            )
            before = controller.kp * error + integral + derivative
            held = (before >= controller.output_max and error > 0) or (
                before <= controller.output_min and error < 0
            )
            integral = integral if held else proposed
            command = _clamp(
                controller.kp * error + integral + derivative,
                controller.output_min,
                controller.output_max,
            )
            previous = output
        trajectory.append(Sample(output, velocity, command))
    return trajectory


def steady_period(states: Sequence[tuple[int, ...]], tail: int) -> tuple[int, int]:
    """Return the period a fixed-point loop settles into and where its cycle starts.

    Parameters
    ----------
    states
        Complete loop state at each sample, in raw integers.
    tail
        Number of final samples to search; the cycle must repeat inside them.

    Returns
    -------
    tuple[int, int]
        Period (1 for a fixed point) and the index of the first state of the repeating cycle.

    Raises
    ------
    ValueError
        If no state repeats within the tail.
    """
    seen: dict[tuple[int, ...], int] = {}
    start = max(len(states) - tail, 0)
    for index in range(start, len(states)):
        first = seen.setdefault(states[index], index)
        if first != index:
            return index - first, first
    message = f"no state repeats within the last {tail} samples"
    raise ValueError(message)


def deviation(
    fixed: Sequence[Sample], reference: Sequence[Sample]
) -> dict[Literal["output", "command"], float]:
    """Return the largest absolute output and command differences of two trajectories.

    Parameters
    ----------
    fixed, reference
        Fixed-point trajectory in real units and the float64 reference of the same length.

    Returns
    -------
    dict
        ``output`` and ``command``: the largest absolute differences.

    Raises
    ------
    ValueError
        If the lengths differ or a trajectory is empty.
    """
    if len(fixed) != len(reference) or not fixed:
        message = "deviation needs two non-empty trajectories of equal length"
        raise ValueError(message)
    return {
        "output": max(abs(a.output - b.output) for a, b in zip(fixed, reference, strict=True)),
        "command": max(abs(a.command - b.command) for a, b in zip(fixed, reference, strict=True)),
    }
