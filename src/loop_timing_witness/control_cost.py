# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — quadratic cost of the benchmark control loops under input-output delay

"""Stationary quadratic cost of a benchmark loop whose command is applied after a random delay.

The cost follows Jitterbug (Lincoln and Cervin, 2002; Cervin, Henriksson, Lincoln, Eker and
Årzén, 2003). The continuous plant ``dx = (A x + B u) dt + dw`` is driven by white noise of
incremental covariance ``R1 dt``. The loop samples it every ``h`` seconds; the command computed
from sample ``k`` is applied ``Δ_k`` seconds after the sample and held until the next command is
applied. The delays are independent, each drawn from one discrete distribution on ``[0, h)``.
The cost is the stationary time average::

    J = lim (1/T) E ∫ (y² + q u²) dt,    T → ∞,

with ``y`` the plant output (the first state), ``u`` the applied command and ``q`` the input
weight, under ``R1 = B B'``: unit-intensity noise entering with the command. ``J`` scales with
the noise intensity, so the ratio of two costs does not depend on it.

The loop state ``z = (x, u, c, v)`` holds the plant state, the applied command, the controller
state and the command computed but not yet applied. Between events the plant integrates
exactly; the block exponentials of Van Loan (1978) give each interval's transition, integrated
cost weight, noise covariance and noise cost. A period with delay ``Δ`` maps the second moment
of ``z`` at a sample, ``P``, to ``M_Δ P M_Δ' + R(h)`` with ``M_Δ = Φ(h-Δ) G Φ(Δ) S``, where ``S``
is the controller update at the sample and ``G`` applies the waiting command. The stationary
moment solves ``P = Σ p_Δ M_Δ P M_Δ' + R(h)``; it exists when the period map is mean-square
stable, which a power of the map with norm below one proves. Saturation, conditional
integration and quantization are left out, as for the timing margins.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil, isfinite, log2
from typing import TYPE_CHECKING, Final

from loop_timing_witness.control_reference import Lqr, Pid

if TYPE_CHECKING:
    from collections.abc import Sequence

    from loop_timing_witness.control_timing import ContinuousPlant

type Matrix = list[list[float]]

PROBABILITY_TOLERANCE: Final = 1e-9
"""Largest accepted difference between the sum of the delay probabilities and one."""

SQUARINGS: Final = 40
"""Squarings of the period map tried to prove mean-square stability, up to ``2**40`` periods."""

_SCALED_NORM: Final = 0.25
"""Largest norm of the scaled matrix whose exponential the Taylor series sums."""

_TAYLOR_TERMS: Final = 30
"""Upper bound on the Taylor terms; at a norm of 0.25 twenty terms reach rounding."""

_DIVERGED: Final = 1e150
"""Norm of a power of the period map beyond which the loop is not mean-square stable."""

_MECHANICAL_ORDER: Final = 3
"""Coefficients of the mechanical model's characteristic polynomial."""

_THERMAL_ORDER: Final = 2
"""Coefficients of the thermal model's characteristic polynomial."""


@dataclass(frozen=True)
class Delay:
    """One value of the input-output delay distribution.

    Attributes
    ----------
    seconds
        Delay from a sample to the application of its command, in ``[0, h)``.
    probability
        Probability of this delay in a period.
    """

    seconds: float
    probability: float


def empirical_delays(latencies: Sequence[float], period: float) -> tuple[Delay, ...]:
    """Return the empirical delay distribution of measured input-output latencies.

    Parameters
    ----------
    latencies
        Measured delays in seconds, each from a sample to its applied command.
    period
        Sample period in seconds.

    Returns
    -------
    tuple[Delay, ...]
        Each distinct latency in increasing order with its relative frequency.

    Raises
    ------
    ValueError
        If there are no latencies, a latency is not finite or lies outside ``[0, period)``, or
        the period is not positive and finite.
    """
    if not latencies or not isfinite(period) or period <= 0:
        message = "an empirical delay distribution needs latencies and a positive period"
        raise ValueError(message)
    if any(not isfinite(value) or not 0 <= value < period for value in latencies):
        message = "every latency must be finite and lie in [0, period)"
        raise ValueError(message)
    counts = Counter(latencies)
    return tuple(Delay(value, counts[value] / len(latencies)) for value in sorted(counts))


def quadratic_cost(
    plant: ContinuousPlant,
    controller: Pid | Lqr,
    delays: Sequence[Delay],
    input_weight: float = 0.0,
) -> float:
    """Return the stationary cost ``J`` of the linear loop under the delay distribution.

    Parameters
    ----------
    plant
        Continuous plant with its sample period: the mechanical or the thermal model.
    controller
        PID acting on the output, or state feedback on every state.
    delays
        Delay distribution; the probabilities sum to one.
    input_weight
        Weight ``q`` of the applied command's square, non-negative.

    Returns
    -------
    float
        ``J`` for unit-intensity noise at the plant input.

    Raises
    ------
    ValueError
        If the plant is not one of the two models, a delay or probability is out of range, the
        probabilities do not sum to one, the input weight is negative, or the loop is not shown
        to be mean-square stable.
    """
    period = plant.period
    _check_delays(delays, period, input_weight)
    a, b = _state_space(plant)
    states = len(b)
    dynamics = [[*a[i], b[i]] for i in range(states)] + [[0.0] * (states + 1)]
    weights = _zeros(states + 1, states + 1)
    weights[0][0], weights[states][states] = 1.0, input_weight
    noise = _zeros(states + 1, states + 1)
    for i in range(states):
        for j in range(states):
            noise[i][j] = b[i] * b[j]
    sample, apply = _event_maps(controller, states)
    size = len(sample)
    cache: dict[float, _Segment] = {}

    def segment(length: float) -> _Segment:
        if length not in cache:
            cache[length] = _segment(dynamics, weights, noise, length, size)
        return cache[length]

    periods = [
        (
            delay.probability,
            _product(
                segment(period - delay.seconds).transition,
                apply,
                segment(delay.seconds).transition,
                sample,
            ),
        )
        for delay in delays
    ]
    moment = _stationary_moment(periods, segment(period).covariance)
    sampled = _product(sample, moment, _transpose(sample))
    total = 0.0
    for delay in delays:
        before, after = segment(delay.seconds), segment(period - delay.seconds)
        applied = _product(
            apply,
            _add(
                _product(before.transition, sampled, _transpose(before.transition)),
                before.covariance,
            ),
            _transpose(apply),
        )
        total += delay.probability * (
            _trace_product(before.weight, sampled)
            + before.noise_cost
            + _trace_product(after.weight, applied)
            + after.noise_cost
        )
    return total / period


def cost_increase(
    plant: ContinuousPlant,
    controller: Pid | Lqr,
    delays: Sequence[Delay],
    input_weight: float = 0.0,
) -> float:
    """Return the relative cost increase of the delay distribution over immediate application.

    Parameters
    ----------
    plant
        Continuous plant with its sample period.
    controller
        PID or state feedback.
    delays
        Delay distribution.
    input_weight
        Weight of the applied command's square.

    Returns
    -------
    float
        ``J(delays) / J(no delay) - 1``; it does not depend on the noise intensity.

    Raises
    ------
    ValueError
        As :func:`quadratic_cost`, for either distribution.
    """
    immediate = quadratic_cost(plant, controller, (Delay(0.0, 1.0),), input_weight)
    return quadratic_cost(plant, controller, delays, input_weight) / immediate - 1


@dataclass(frozen=True)
class _Segment:
    """Exact quantities of one interval without events, embedded in the loop state.

    Attributes
    ----------
    transition
        ``Φ(L)``: the plant integrates the held command; the other states stay.
    weight
        ``∫ Φ(t)' Q Φ(t) dt`` over the interval.
    covariance
        Noise covariance ``R(L) = ∫ Φ(t) R1 Φ(t)' dt`` accumulated over the interval.
    noise_cost
        ``∫ tr(Q R(t)) dt`` over the interval.
    """

    transition: Matrix
    weight: Matrix
    covariance: Matrix
    noise_cost: float


def _check_delays(delays: Sequence[Delay], period: float, input_weight: float) -> None:
    """Refuse a delay distribution or input weight that the cost does not cover.

    Parameters
    ----------
    delays
        Delay distribution.
    period
        Sample period in seconds.
    input_weight
        Weight of the applied command's square.

    Raises
    ------
    ValueError
        If a delay lies outside ``[0, period)``, a probability is not positive and finite, the
        probabilities do not sum to one, or the input weight is negative or not finite.
    """
    if not delays or any(
        not isfinite(delay.seconds)
        or not 0 <= delay.seconds < period
        or not isfinite(delay.probability)
        or delay.probability <= 0
        for delay in delays
    ):
        message = "every delay must lie in [0, period) with a positive, finite probability"
        raise ValueError(message)
    if abs(sum(delay.probability for delay in delays) - 1) > PROBABILITY_TOLERANCE:
        message = "the delay probabilities must sum to one"
        raise ValueError(message)
    if not isfinite(input_weight) or input_weight < 0:
        message = "the input weight must be finite and non-negative"
        raise ValueError(message)


def _state_space(plant: ContinuousPlant) -> tuple[Matrix, list[float]]:
    """Return ``A`` and ``B`` of the mechanical or the thermal model in its physical states.

    Parameters
    ----------
    plant
        Continuous plant from ``control_timing``.

    Returns
    -------
    tuple
        ``A`` and ``B``: position and velocity of ``m x'' + c x' + k x = u``, or the temperature
        of ``theta' = (-theta + gain u)/tau``.

    Raises
    ------
    ValueError
        If the plant has neither model's form.
    """
    if (
        plant.numerator == ((1.0,), (0.0, 1.0))
        and len(plant.denominator) == _MECHANICAL_ORDER
        and plant.denominator[-1] > 0
    ):
        stiffness, damping, mass = plant.denominator
        return [[0.0, 1.0], [-stiffness / mass, -damping / mass]], [0.0, 1.0 / mass]
    if (
        len(plant.numerator) == 1
        and len(plant.numerator[0]) == 1
        and len(plant.denominator) == _THERMAL_ORDER
        and plant.denominator[-1] > 0
    ):
        constant, tau = plant.denominator
        return [[-constant / tau]], [plant.numerator[0][0] / tau]
    message = "the cost covers the mechanical and the thermal plant models"
    raise ValueError(message)


def _event_maps(controller: Pid | Lqr, states: int) -> tuple[Matrix, Matrix]:
    """Return the sample update ``S`` and the command application ``G`` on ``z = (x, u, c, v)``.

    The PID's state is its integral, derivative and previous output; at a sample it reads the
    output, updates its state and computes the command ``v``. State feedback has no state.

    Parameters
    ----------
    controller
        PID or state feedback in real units, with a zero reference.
    states
        Plant states.

    Returns
    -------
    tuple
        ``S`` and ``G``.
    """
    if isinstance(controller, Lqr):
        dynamics: Matrix = []
        reads: Matrix = []
        command_state: list[float] = []
        command_reads = [-controller.kx, -controller.kv][:states]
    else:
        ki, decay, gain = controller.ki_period, controller.decay, controller.derivative_gain
        dynamics = [[1.0, 0.0, 0.0], [0.0, decay, gain], [0.0, 0.0, 0.0]]
        rest = [0.0] * (states - 1)
        reads = [[-ki, *rest], [-gain, *rest], [1.0, *rest]]
        command_state = [1.0, decay, gain]
        command_reads = [-(controller.kp + ki + gain), *rest]
    memory = len(dynamics)
    size = states + memory + 2
    sample = _identity(size)
    for i in range(memory):
        row = states + 1 + i
        sample[row] = [*reads[i], 0.0, *dynamics[i], 0.0]
    sample[size - 1] = [*command_reads, 0.0, *command_state, 0.0]
    apply = _identity(size)
    apply[states] = [0.0] * (size - 1) + [1.0]
    return sample, apply


def _segment(
    dynamics: Matrix, weights: Matrix, noise: Matrix, length: float, size: int
) -> _Segment:
    """Return one interval's exact quantities from Van Loan's block exponentials.

    With ``F`` the dynamics of ``(x, u)``, the exponential of
    ``[[-F', I, 0], [0, -F', Q], [0, 0, F]] L`` has ``Φ = e^{FL}`` as its last diagonal block;
    ``Φ'`` times its middle-right block is ``∫ Φ(t)' Q Φ(t) dt`` and ``Φ'`` times its top-right
    block is ``∫ (L - t) Φ(t)' Q Φ(t) dt``, whose product with ``R1`` has the noise cost as its
    trace. The exponential of ``[[-F, R1], [0, F']] L`` gives ``R(L)`` the same way.

    Parameters
    ----------
    dynamics
        ``F`` of the plant state and the held command.
    weights
        Cost weight ``Q`` of ``(x, u)``.
    noise
        Noise intensity ``R1`` of ``(x, u)``.
    length
        Interval in seconds.
    size
        Size of the loop state the quantities are embedded in.

    Returns
    -------
    _Segment
        Transition, integrated weight, noise covariance and noise cost.
    """
    order = len(dynamics)
    minus = [[-dynamics[j][i] for j in range(order)] for i in range(order)]
    zero, one = _zeros(order, order), _identity(order)
    cost = _expm(
        _scaled(
            _blocks([[minus, one, zero], [zero, minus, weights], [zero, zero, dynamics]]), length
        )
    )
    covariance = _expm(
        _scaled(_blocks([[_scaled(dynamics, -1.0), noise], [zero, _transpose(dynamics)]]), length)
    )
    transition = _part(cost, 2, 2, order)
    back = _transpose(transition)
    integral = _mul(back, _part(cost, 1, 2, order))
    double = _mul(back, _part(cost, 0, 2, order))
    accumulated = _mul(_transpose(_part(covariance, 1, 1, order)), _part(covariance, 0, 1, order))
    return _Segment(
        _embed(transition, size, identity=True),
        _embed(_symmetric(integral), size, identity=False),
        _embed(_symmetric(accumulated), size, identity=False),
        _trace_product(double, noise),
    )


def _stationary_moment(periods: Sequence[tuple[float, Matrix]], noise: Matrix) -> Matrix:
    """Solve ``P = Σ p M P M' + R(h)`` after proving the period map mean-square stable.

    Parameters
    ----------
    periods
        Probability and period map ``M`` of each delay.
    noise
        Noise covariance ``R(h)`` of one period.

    Returns
    -------
    Matrix
        Stationary second moment of the loop state at a sample, before the controller update.

    Raises
    ------
    ValueError
        If no power of the period map up to ``2**SQUARINGS`` has an infinity norm below one.
    """
    size = len(noise)
    operator = _zeros(size * size, size * size)
    for probability, period in periods:
        for i in range(size):
            for k in range(size):
                row = operator[i * size + k]
                for j in range(size):
                    scale = probability * period[i][j]
                    if scale:
                        for column in range(size):
                            row[j * size + column] += scale * period[k][column]
    _require_mean_square_stable(operator)
    system = [
        [(1.0 if i == j else 0.0) - operator[i][j] for j in range(size * size)]
        for i in range(size * size)
    ]
    flat = _solve(system, [noise[i][k] for i in range(size) for k in range(size)])
    return _symmetric([flat[i * size : (i + 1) * size] for i in range(size)])


def _require_mean_square_stable(operator: Matrix) -> None:
    """Prove that the second-moment map's spectral radius is below one.

    The spectral radius of ``T`` is at most ``||T^n||^(1/n)`` for every ``n``, so one power with
    infinity norm below one proves stability. The powers ``T^(2^k)`` are formed by repeated
    squaring.

    Parameters
    ----------
    operator
        Second-moment map ``T`` of one period on the flattened moment.

    Raises
    ------
    ValueError
        If no power up to ``T^(2^SQUARINGS)`` has norm below one, or the powers diverge.
    """
    power = operator
    for _ in range(SQUARINGS + 1):
        norm = max(sum(abs(value) for value in row) for row in power)
        if norm < 1:
            return
        if norm > _DIVERGED:
            break
        power = _mul(power, power)
    message = "the loop is not shown to be mean-square stable under this delay distribution"
    raise ValueError(message)


def _expm(matrix: Matrix) -> Matrix:
    """Return the matrix exponential by scaling, a Taylor series and repeated squaring.

    Parameters
    ----------
    matrix
        Square matrix.

    Returns
    -------
    Matrix
        ``e^matrix``.
    """
    norm = max(sum(abs(value) for value in row) for row in matrix)
    squarings = max(0, ceil(log2(norm / _SCALED_NORM))) if norm > _SCALED_NORM else 0
    scaled = _scaled(matrix, 2.0**-squarings)
    result = _identity(len(matrix))
    term = _identity(len(matrix))
    for order in range(1, _TAYLOR_TERMS + 1):
        term = _scaled(_mul(term, scaled), 1.0 / order)
        result = _add(result, term)
        if max(abs(value) for row in term for value in row) == 0:
            break
    for _ in range(squarings):
        result = _mul(result, result)
    return result


def _solve(matrix: Matrix, right: list[float]) -> list[float]:
    """Solve a linear system by Gaussian elimination with partial pivoting.

    Parameters
    ----------
    matrix
        Square, non-singular coefficient matrix; it is not modified.
    right
        Right-hand side.

    Returns
    -------
    list[float]
        Solution.
    """
    size = len(matrix)
    rows = [[*matrix[i], right[i]] for i in range(size)]
    for column in range(size):
        pivot = column
        for row in range(column + 1, size):
            if abs(rows[row][column]) > abs(rows[pivot][column]):
                pivot = row
        rows[column], rows[pivot] = rows[pivot], rows[column]
        lead = rows[column]
        for row in range(column + 1, size):
            factor = rows[row][column] / lead[column]
            if factor:
                target = rows[row]
                for index in range(column, size + 1):
                    target[index] -= factor * lead[index]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        known = sum(rows[row][index] * solution[index] for index in range(row + 1, size))
        solution[row] = (rows[row][size] - known) / rows[row][row]
    return solution


def _identity(size: int) -> Matrix:
    """Return the identity matrix of ``size``."""
    return [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]


def _zeros(rows: int, columns: int) -> Matrix:
    """Return a zero matrix."""
    return [[0.0] * columns for _ in range(rows)]


def _transpose(matrix: Matrix) -> Matrix:
    """Return the transpose."""
    return [list(column) for column in zip(*matrix, strict=True)]


def _mul(left: Matrix, right: Matrix) -> Matrix:
    """Return the matrix product."""
    columns = _transpose(right)
    return [
        [sum(x * y for x, y in zip(row, column, strict=True)) for column in columns] for row in left
    ]


def _product(*factors: Matrix) -> Matrix:
    """Return the product of the factors from left to right."""
    result = factors[0]
    for factor in factors[1:]:
        result = _mul(result, factor)
    return result


def _add(left: Matrix, right: Matrix) -> Matrix:
    """Return the matrix sum."""
    return [[x + y for x, y in zip(a, b, strict=True)] for a, b in zip(left, right, strict=True)]


def _scaled(matrix: Matrix, factor: float) -> Matrix:
    """Return the matrix times a scalar."""
    return [[factor * value for value in row] for row in matrix]


def _symmetric(matrix: Matrix) -> Matrix:
    """Return the symmetric part, which removes rounding asymmetry."""
    size = len(matrix)
    return [[(matrix[i][j] + matrix[j][i]) / 2 for j in range(size)] for i in range(size)]


def _trace_product(left: Matrix, right: Matrix) -> float:
    """Return ``tr(left right)``."""
    return sum(left[i][j] * right[j][i] for i in range(len(left)) for j in range(len(right)))


def _blocks(grid: Sequence[Sequence[Matrix]]) -> Matrix:
    """Assemble a block matrix from rows of equally sized square blocks."""
    return [
        [value for block in row for value in block[line]]
        for row in grid
        for line in range(len(row[0]))
    ]


def _part(matrix: Matrix, row: int, column: int, order: int) -> Matrix:
    """Return block ``(row, column)`` of a matrix of ``order``-sized square blocks."""
    return [
        line[column * order : (column + 1) * order]
        for line in matrix[row * order : (row + 1) * order]
    ]


def _embed(block: Matrix, size: int, *, identity: bool) -> Matrix:
    """Place a block in the top-left corner of the identity or the zero matrix of ``size``."""
    result = _identity(size) if identity else _zeros(size, size)
    for i, line in enumerate(block):
        result[i][: len(line)] = line
    return result
