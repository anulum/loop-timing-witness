# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — quadratic cost of the benchmark control loops under input-output delay

"""Check the stationary quadratic cost against independent computations of the same loops."""

from __future__ import annotations

from math import exp, expm1, inf, nan, sqrt
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.control_cost import (
    Delay,
    cost_increase,
    empirical_delays,
    quadratic_cost,
)
from loop_timing_witness.control_reference import (
    Lqr,
    Pid,
    default_pid,
    lqr,
    mechanical_plant,
    thermal_plant,
)
from loop_timing_witness.control_timing import (
    ContinuousPlant,
    mechanical_continuous,
    thermal_continuous,
)

if TYPE_CHECKING:
    from collections.abc import Callable

PERIOD = 0.001
GAUSS_NODES = (
    (-0.9602898564975363, 0.1012285362903763),
    (-0.7966664774136267, 0.2223810344533745),
    (-0.5255324099163290, 0.3137066458778873),
    (-0.1834346424956498, 0.3626837833783620),
    (0.1834346424956498, 0.3626837833783620),
    (0.5255324099163290, 0.3137066458778873),
    (0.7966664774136267, 0.2223810344533745),
    (0.9602898564975363, 0.1012285362903763),
)
"""Eight-point Gauss–Legendre rule on [-1, 1]: exact for polynomials up to degree 15."""


def _mechanical(period: float = PERIOD) -> ContinuousPlant:
    """Return ``x'' + x' + x = u`` sampled every ``period`` seconds.

    Parameters
    ----------
    period
        Sample period in seconds.

    Returns
    -------
    ContinuousPlant
        The default mechanical plant.
    """
    return mechanical_continuous(mechanical_plant(period), period)


def _thermal() -> ContinuousPlant:
    """Return ``theta' = -theta + u`` sampled every millisecond.

    Returns
    -------
    ContinuousPlant
        The default thermal plant.
    """
    return thermal_continuous(thermal_plant(PERIOD), PERIOD)


def _integral(function: Callable[[float], float], start: float, end: float) -> float:
    """Integrate a smooth function with the eight-point Gauss–Legendre rule.

    Parameters
    ----------
    function
        Callable of one float.
    start, end
        Interval.

    Returns
    -------
    float
        The integral.
    """
    half, middle = (end - start) / 2, (end + start) / 2
    return half * sum(weight * function(middle + half * node) for node, weight in GAUSS_NODES)


type _Square = list[list[float]]

_GRID_STATES = 7
"""Position, velocity, applied command, integral, derivative, previous output, waiting command."""


def _unit(size: int) -> _Square:
    """Return the identity matrix of ``size``."""
    return [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]


def _mul(left: _Square, right: _Square) -> _Square:
    """Return the matrix product."""
    columns = list(zip(*right, strict=True))
    return [
        [sum(x * y for x, y in zip(row, column, strict=True)) for column in columns] for row in left
    ]


def _congruent(left: _Square, moment: _Square) -> _Square:
    """Return ``left moment left'``."""
    return _mul(_mul(left, moment), [list(row) for row in zip(*left, strict=True)])


def _add(left: _Square, right: _Square) -> _Square:
    """Return the matrix sum."""
    return [[x + y for x, y in zip(a, b, strict=True)] for a, b in zip(left, right, strict=True)]


def _unit_noise(t: float) -> float:
    """Return the variance unit-intensity noise gives ``theta' = -theta + w`` after ``t``."""
    return -expm1(-2 * t) / 2


def _thermal_period(gain: float, d: float) -> tuple[_Square, float]:
    """Return one period's map of ``(theta_k, held command)`` and the noise variance it adds.

    ``theta(d) = e^{-d} theta_k + (1 - e^{-d}) held``; from ``d`` on the command
    ``-gain*theta_k`` acts and becomes the next held command.

    Parameters
    ----------
    gain
        Feedback gain.
    d
        Delay in seconds.

    Returns
    -------
    tuple
        The two-by-two map and the variance added to ``theta`` at the next sample.
    """
    rest = PERIOD - d
    full = [[exp(-PERIOD) + gain * expm1(-rest), -exp(-rest) * expm1(-d)], [-gain, 0.0]]
    return full, exp(-2 * rest) * _unit_noise(d) + _unit_noise(rest)


def _thermal_moment(gain: float, delays: list[tuple[float, float]]) -> _Square:
    """Iterate the second moment of ``(theta_k, held command)`` to its fixed point.

    Parameters
    ----------
    gain
        Feedback gain.
    delays
        ``(delay, probability)`` pairs.

    Returns
    -------
    list
        Stationary second moment at a sample.
    """
    maps = [(probability, *_thermal_period(gain, d)) for d, probability in delays]
    second = [[0.0, 0.0], [0.0, 0.0]]
    for _ in range(200_000):
        following = [[0.0, 0.0], [0.0, 0.0]]
        for probability, full, variance in maps:
            moved = _congruent(full, second)
            for i in range(2):
                for k in range(2):
                    following[i][k] += probability * moved[i][k]
            following[0][0] += probability * variance
        if max(abs(following[i][k] - second[i][k]) for i in range(2) for k in range(2)) < 1e-17:
            return following
        second = following
    pytest.fail("the elementary moment iteration did not converge")


def _thermal_period_cost(gain: float, d: float, second: _Square) -> float:
    """Integrate the mean square of ``theta`` over one period whose command waits ``d``.

    Parameters
    ----------
    gain
        Feedback gain.
    d
        Delay in seconds.
    second
        Stationary second moment of ``(theta_k, held command)``.

    Returns
    -------
    float
        ``∫ E theta(t)² dt`` over the period.
    """
    theta2, cross, held2 = second[0][0], second[0][1], second[1][1]

    def before(t: float) -> float:
        a, b = exp(-t), -expm1(-t)
        return a * a * theta2 + 2 * a * b * cross + b * b * held2 + _unit_noise(t)

    at_d, mixed = before(d), exp(-d) * theta2 - expm1(-d) * cross

    def later(t: float) -> float:
        a, b = exp(-(t - d)), gain * expm1(-(t - d))
        return a * a * at_d + 2 * a * b * mixed + b * b * theta2 + _unit_noise(t - d)

    return _integral(before, 0.0, d) + _integral(later, d, PERIOD)


def _thermal_feedback_cost(gain: float, delays: list[tuple[float, float]]) -> float:
    """Compute the thermal state-feedback loop's cost from elementary exponentials.

    For ``theta' = -theta + u + w`` with ``u = -gain*theta_k`` applied ``d`` after sample ``k``,
    the pair ``(theta_k, held command)`` evolves linearly over a period; its stationary second
    moment is iterated to its fixed point, and the cost integrates the explicit mean square of
    ``theta(t)`` over the two parts of each period.

    Parameters
    ----------
    gain
        Feedback gain.
    delays
        ``(delay, probability)`` pairs.

    Returns
    -------
    float
        Stationary time average of ``theta²`` for unit-intensity input noise.
    """
    second = _thermal_moment(gain, delays)
    return sum(p * _thermal_period_cost(gain, d, second) for d, p in delays) / PERIOD


def _grid_step(length: float) -> _Square:
    """Return the closed-form zero-order-hold move of the mechanical plant in the loop state.

    Parameters
    ----------
    length
        Substep in seconds.

    Returns
    -------
    list
        Transition of the seven loop states over the substep.
    """
    moved = mechanical_plant(length)
    step = _unit(_GRID_STATES)
    step[0][:3] = [moved.transition[0][0], moved.transition[0][1], moved.input[0]]
    step[1][:3] = [moved.transition[1][0], moved.transition[1][1], moved.input[1]]
    return step


def _grid_noise(length: float) -> _Square:
    """Return Simpson's rule for ``∫ e^{As} B B' e^{A's} ds`` with the closed-form ``e^{As} B``.

    Parameters
    ----------
    length
        Substep in seconds.

    Returns
    -------
    list
        Noise covariance of the substep in the loop state.
    """
    impulses = [(0.0, 1.0)] + [
        (mechanical_plant(s).transition[0][1], mechanical_plant(s).transition[1][1])
        for s in (length / 2, length)
    ]
    noise = [[0.0] * _GRID_STATES for _ in range(_GRID_STATES)]
    for i in range(2):
        for k in range(2):
            noise[i][k] = (
                length
                / 6
                * (
                    impulses[0][i] * impulses[0][k]
                    + 4 * impulses[1][i] * impulses[1][k]
                    + impulses[2][i] * impulses[2][k]
                )
            )
    return noise


def _grid_events() -> tuple[_Square, _Square]:
    """Return the default PID's sample update and the command application on the loop state.

    Returns
    -------
    tuple
        Sample update and application, both seven by seven.
    """
    pid = default_pid()
    ki, decay, gain = pid.ki_period, pid.decay, pid.derivative_gain
    sample = _unit(_GRID_STATES)
    sample[3] = [-ki, 0, 0, 1, 0, 0, 0]
    sample[4] = [-gain, 0, 0, 0, decay, gain, 0]
    sample[5] = [1, 0, 0, 0, 0, 0, 0]
    sample[6] = [-(pid.kp + ki + gain), 0, 0, 1, decay, gain, 0]
    apply = _unit(_GRID_STATES)
    apply[2] = [0, 0, 0, 0, 0, 0, 1]
    return sample, apply


def _grid_moment(delay_steps: int, steps: int) -> _Square:
    """Return the stationary moment at a sample by the doubling algorithm for ``P = M P M' + R``.

    Parameters
    ----------
    delay_steps
        Substeps between a sample and the application of its command.
    steps
        Substeps per period.

    Returns
    -------
    list
        Stationary second moment of the loop state at a sample, before the controller update.
    """
    sample, apply = _grid_events()
    step, noise = _grid_step(PERIOD / steps), _grid_noise(PERIOD / steps)
    period_map, accumulated = sample, [[0.0] * _GRID_STATES for _ in range(_GRID_STATES)]
    for index in range(steps):
        if index == delay_steps:
            period_map, accumulated = _mul(apply, period_map), _congruent(apply, accumulated)
        period_map = _mul(step, period_map)
        accumulated = _add(_congruent(step, accumulated), noise)
    moment, power = accumulated, period_map
    for _ in range(40):
        moment, power = _add(moment, _congruent(power, moment)), _mul(power, power)
    return moment


def _mechanical_pid_cost(delay_steps: int, steps: int) -> float:
    """Compute the mechanical PID loop's cost on a fine grid with a constant delay.

    The plant moves by the closed-form zero-order-hold transition of ``mechanical_plant`` over
    each of ``steps`` substeps; the noise covariance and the cost are Simpson integrals; the
    stationary moment comes from the doubling algorithm.

    Parameters
    ----------
    delay_steps
        Substeps between a sample and the application of its command.
    steps
        Substeps per period.

    Returns
    -------
    float
        Stationary time average of the position squared for unit-intensity input noise.
    """
    sample, apply = _grid_events()
    small = PERIOD / steps
    step, noise = _grid_step(small), _grid_noise(small)
    half, half_noise = _grid_step(small / 2), _grid_noise(small / 2)
    state = _congruent(sample, _grid_moment(delay_steps, steps))
    cost = 0.0
    for index in range(steps):
        if index == delay_steps:
            state = _congruent(apply, state)
        middle = _add(_congruent(half, state), half_noise)
        following = _add(_congruent(step, state), noise)
        cost += small / 6 * (state[0][0] + 4 * middle[0][0] + following[0][0])
        state = following
    return cost / PERIOD


@pytest.mark.parametrize(
    ("model", "mode", "immediate", "increases"),
    [
        ("mechanical", "pid", 0.250188, (3.504e-4, 1.754e-3, 3.478e-3)),
        ("mechanical", "lqr", 0.0586266, (9.010e-5, 4.507e-4, 8.930e-4)),
        ("thermal", "pid", 0.16675, (2.336e-4, 1.168e-3, 2.311e-3)),
        ("thermal", "lqr", 0.3537, (4.138e-5, 2.068e-4, 4.095e-4)),
    ],
)
def test_a_delay_inside_one_period_barely_changes_the_default_loops_cost(
    model: str, mode: str, immediate: float, increases: tuple[float, float, float]
) -> None:
    """The documented costs: a delay of up to one period raises them by less than 0.35 %.

    Parameters
    ----------
    model, mode
        Plant model and controller.
    immediate
        Output variance with the command applied at the sample.
    increases
        Relative increases for constant delays of 0.1, 0.5 and 0.99 periods.
    """
    plant = _thermal() if model == "thermal" else _mechanical()
    weights = (1.0,) if model == "thermal" else (10.0, 1.0)
    controller: Pid | Lqr = lqr(plant.discrete, weights) if mode == "lqr" else default_pid()
    assert quadratic_cost(plant, controller, (Delay(0.0, 1.0),)) == pytest.approx(
        immediate, rel=1e-5
    )
    measured = [
        cost_increase(plant, controller, (Delay(fraction * PERIOD, 1.0),))
        for fraction in (0.1, 0.5, 0.99)
    ]
    assert measured == pytest.approx(increases, rel=1e-3)
    assert measured == sorted(measured)
    assert cost_increase(plant, controller, (Delay(0.0, 1.0),)) == 0


@pytest.mark.parametrize(
    "delays",
    [
        [(0.0, 1.0)],
        [(0.4 * PERIOD, 1.0)],
        [(0.0, 0.2), (0.3 * PERIOD, 0.5), (0.9 * PERIOD, 0.3)],
    ],
)
def test_the_thermal_feedback_cost_equals_its_elementary_computation(
    delays: list[tuple[float, float]],
) -> None:
    """Van Loan's exponentials and the moment equation agree with closed-form exponentials.

    A stronger gain than the default makes the loop settle within a few thousand periods, so
    the elementary computation's fixed-point iteration converges.

    Parameters
    ----------
    delays
        ``(delay, probability)`` pairs, constant and random.
    """
    gain = 200.0
    controller = Lqr(gain, 0.0, 0.0, -4.0, 4.0)
    expected = _thermal_feedback_cost(gain, delays)
    actual = quadratic_cost(_thermal(), controller, [Delay(d, p) for d, p in delays])
    assert actual == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("delay_steps", [0, 37, 199])
def test_the_mechanical_pid_cost_equals_a_fine_grid_computation(delay_steps: int) -> None:
    """The PID's three states, the waiting command and its application agree with a fine grid.

    Parameters
    ----------
    delay_steps
        Substeps of ``PERIOD/200`` between a sample and its command's application.
    """
    expected = _mechanical_pid_cost(delay_steps, 200)
    actual = quadratic_cost(_mechanical(), default_pid(), (Delay(delay_steps * PERIOD / 200, 1.0),))
    assert actual == pytest.approx(expected, rel=1e-8)


def test_the_cost_scales_its_exponentials_for_a_long_period() -> None:
    """With a one-second period the exponentials are scaled and squared; the cost stays exact.

    A long period also makes timing matter: a delay of half the period raises the cost of the
    LQR designed for that period by more than a tenth.
    """
    plant = _mechanical(1.0)
    controller = lqr(plant.discrete, (10.0, 1.0))
    immediate = quadratic_cost(plant, controller, (Delay(0.0, 1.0),))
    assert 0 < immediate < inf
    assert cost_increase(plant, controller, (Delay(0.5, 1.0),)) > 0.1


def test_the_input_weight_adds_the_command_variance_linearly() -> None:
    """``J(q) = J(0) + q * Var(u)``, so the cost is affine in the input weight."""
    plant, controller = _mechanical(), default_pid()
    delays = (Delay(0.0, 0.5), Delay(0.5 * PERIOD, 0.5))
    costs = [quadratic_cost(plant, controller, delays, weight) for weight in (0.0, 1.0, 3.0)]
    assert costs[1] > costs[0]
    assert costs[2] - costs[0] == pytest.approx(3 * (costs[1] - costs[0]), rel=1e-9)


def test_measured_latencies_become_the_empirical_distribution() -> None:
    """Equal latencies merge in increasing order; their cost is that of the stated distribution."""
    latencies = [3e-4, 1e-4, 3e-4, 0.0, 3e-4]
    delays = empirical_delays(latencies, PERIOD)
    assert delays == (Delay(0.0, 0.2), Delay(1e-4, 0.2), Delay(3e-4, 0.6))
    reordered = (Delay(3e-4, 0.6), Delay(0.0, 0.2), Delay(1e-4, 0.2))
    plant, controller = _thermal(), default_pid()
    assert quadratic_cost(plant, controller, delays) == pytest.approx(
        quadratic_cost(plant, controller, reordered), rel=1e-12
    )


@pytest.mark.parametrize(
    ("latencies", "period"),
    [
        ([], PERIOD),
        ([1e-4], 0.0),
        ([1e-4], nan),
        ([-1e-4], PERIOD),
        ([PERIOD], PERIOD),
        ([inf], PERIOD),
    ],
)
def test_empirical_delays_refuse_latencies_outside_one_period(
    latencies: list[float], period: float
) -> None:
    """Latencies must be finite and inside ``[0, period)``, and the period positive.

    Parameters
    ----------
    latencies, period
        Refused input.
    """
    with pytest.raises(ValueError, match="latenc"):
        empirical_delays(latencies, period)


@pytest.mark.parametrize(
    ("delays", "weight", "message"),
    [
        ((), 0.0, "every delay"),
        ((Delay(PERIOD, 1.0),), 0.0, "every delay"),
        ((Delay(-1e-6, 1.0),), 0.0, "every delay"),
        ((Delay(nan, 1.0),), 0.0, "every delay"),
        ((Delay(0.0, 0.0), Delay(1e-4, 1.0)), 0.0, "every delay"),
        ((Delay(0.0, inf),), 0.0, "every delay"),
        ((Delay(0.0, 0.5), Delay(1e-4, 0.4)), 0.0, "sum to one"),
        ((Delay(0.0, 1.0),), -1.0, "input weight"),
        ((Delay(0.0, 1.0),), nan, "input weight"),
    ],
)
def test_the_cost_refuses_distributions_and_weights_it_does_not_cover(
    delays: tuple[Delay, ...], weight: float, message: str
) -> None:
    """Delays outside one period, invalid probabilities and negative weights are refused.

    Parameters
    ----------
    delays, weight
        Refused input.
    message
        Expected part of the refusal.
    """
    with pytest.raises(ValueError, match=message):
        quadratic_cost(_thermal(), default_pid(), delays, weight)


def test_the_cost_refuses_a_plant_of_another_form() -> None:
    """Only the mechanical and the thermal model have a known state-space form."""
    plant = ContinuousPlant(((1.0,), (1.0,)), (1.0, 1.0, 1.0), mechanical_plant(PERIOD), PERIOD)
    with pytest.raises(ValueError, match="mechanical and the thermal"):
        quadratic_cost(plant, default_pid(), (Delay(0.0, 1.0),))


def test_a_loop_that_a_delay_destabilises_has_no_stationary_cost() -> None:
    """A gain stable with immediate application diverges with a delay near one period.

    ``theta_{k+1} = phi*theta_k - gamma*K*theta_{k-1}`` is unstable for ``gamma*K > 1``, while
    immediate application gives the stable pole ``phi - gamma*K`` for ``gamma*K < 1 + phi``.
    """
    plant = _thermal()
    gamma = plant.discrete.input[0]
    controller = Lqr(1.5 / gamma, 0.0, 0.0, -4.0, 4.0)
    assert 0 < quadratic_cost(plant, controller, (Delay(0.0, 1.0),)) < inf
    with pytest.raises(ValueError, match="mean-square stable"):
        quadratic_cost(plant, controller, (Delay(0.99 * PERIOD, 1.0),))


def test_a_marginally_stable_loop_is_not_shown_stable() -> None:
    """An undamped double integrator without feedback grows polynomially, never below norm one."""
    plant = ContinuousPlant(((1.0,), (0.0, 1.0)), (0.0, 0.0, 1.0), mechanical_plant(PERIOD), PERIOD)
    with pytest.raises(ValueError, match="mean-square stable"):
        quadratic_cost(plant, Lqr(0.0, 0.0, 0.0, -4.0, 4.0), (Delay(0.0, 1.0),))


def test_unit_noise_makes_the_thermal_open_loop_variance_one_half() -> None:
    """Without feedback ``theta' = -theta + w`` has stationary variance ``1/2`` at every instant."""
    cost = quadratic_cost(_thermal(), Lqr(0.0, 0.0, 0.0, -4.0, 4.0), (Delay(0.0, 1.0),))
    assert cost == pytest.approx(0.5, rel=1e-9)
    assert sqrt(cost) == pytest.approx(sqrt(0.5), rel=1e-9)
