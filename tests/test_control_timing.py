# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — delay and jitter margins of the benchmark control loops

"""Check the timing margins of the benchmark loops, partly against direct simulation."""

from __future__ import annotations

from collections import deque
from math import floor, inf, nan, sqrt

import pytest

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
    Margins,
    latency_verdict,
    margins,
    mechanical_continuous,
    thermal_continuous,
)

PERIOD = 0.001


def _mechanical() -> ContinuousPlant:
    """Return the default mechanical plant.

    Returns
    -------
    ContinuousPlant
        ``x'' + x' + x = u`` sampled every millisecond.
    """
    return mechanical_continuous(mechanical_plant(PERIOD), PERIOD)


def _thermal() -> ContinuousPlant:
    """Return the default thermal plant.

    Returns
    -------
    ContinuousPlant
        ``theta' = -theta + u`` sampled every millisecond.
    """
    return thermal_continuous(thermal_plant(PERIOD), PERIOD)


@pytest.mark.parametrize(
    ("model", "mode", "delay", "jitter"),
    [
        ("mechanical", "pid", 335.07243, 312.77916),
        ("mechanical", "lqr", 715.23010, 605.95757),
        ("thermal", "pid", 993.00977, 427.97961),
        ("thermal", "lqr", None, 2415.42175),
    ],
)
def test_default_loops_tolerate_hundreds_of_sample_periods(
    model: str, mode: str, delay: float | None, jitter: float
) -> None:
    """The default loops' margins, and the jitter margin never above the delay margin.

    The crossover lies near 0.002 rad per sample, so a delay of hundreds of periods is needed
    to destabilize any default loop. Property 2 of the jitter-margin paper bounds the jitter
    margin by the delay margin; without a crossover the delay margin is unbounded.

    Parameters
    ----------
    model, mode
        Plant model and controller.
    delay, jitter
        Expected delay and jitter margins in sample periods.
    """
    plant = _thermal() if model == "thermal" else _mechanical()
    weights = (1.0,) if model == "thermal" else (10.0, 1.0)
    controller: Pid | Lqr = lqr(plant.discrete, weights) if mode == "lqr" else default_pid()
    result = margins(plant, controller)
    assert result.jitter_margin == pytest.approx(jitter, rel=1e-6)
    if delay is None:
        assert (result.crossover, result.phase_margin, result.delay_margin) == (None, None, None)
    else:
        assert result.delay_margin is not None
        assert result.delay_margin == pytest.approx(delay, rel=1e-6)
        assert result.jitter_margin < result.delay_margin
        assert result.crossover is not None
        assert 0.001 < result.crossover < 0.003


def _envelope_growth(delay: int) -> float:
    """Simulate the linear default mechanical PID loop with a constant command delay.

    Parameters
    ----------
    delay
        Whole sample periods between a sample and the use of its command.

    Returns
    -------
    float
        Ratio of the largest output magnitude in the last 100,000 samples to that in the
        100,000 before them.
    """
    plant, pid = mechanical_plant(PERIOD), default_pid()
    a, b = plant.transition, plant.input
    position, velocity, integral, derivative, previous = 0.01, 0.0, 0.0, 0.0, 0.01
    queue = deque([0.0] * delay)
    windows = [0.0, 0.0]
    for index in range(400_000):
        derivative = pid.decay * derivative - pid.derivative_gain * (position - previous)
        integral -= pid.ki_period * position
        queue.append(-pid.kp * position + integral + derivative)
        previous = position
        command = queue.popleft()
        position, velocity = (
            a[0][0] * position + a[0][1] * velocity + b[0] * command,
            a[1][0] * position + a[1][1] * velocity + b[1] * command,
        )
        if index >= 200_000:
            window = 0 if index < 300_000 else 1
            windows[window] = max(windows[window], abs(position))
    return windows[1] / windows[0]


def test_simulated_constant_delays_bracket_the_delay_margin() -> None:
    """Direct simulation decays one period below the computed margin and grows one above it."""
    margin = margins(_mechanical(), default_pid()).delay_margin
    assert margin is not None
    assert _envelope_growth(floor(margin) - 1) < 1
    assert _envelope_growth(floor(margin) + 1) > 1


def test_unstable_delay_free_loop_is_refused() -> None:
    """A state gain that moves the thermal pole outside the unit circle is refused."""
    with pytest.raises(ValueError, match="delay-free closed loop is not stable"):
        margins(_thermal(), Lqr(3000.0, 0.0, 1.0, -4.0, 4.0))


def test_unstable_mechanical_pid_is_refused() -> None:
    """A negative proportional gain makes the mechanical loop positive feedback and is refused."""
    controller = Pid(-5.0, 0.001, 0.5, 0.25, -4.0, 4.0, -2.0, 2.0)
    with pytest.raises(ValueError, match="delay-free closed loop is not stable"):
        margins(_mechanical(), controller)


def test_jitter_margin_inverts_the_paper_rounding() -> None:
    """The jitter margin ``N`` gives back the bound ``Ñ`` the frequency condition allows."""
    result = margins(_thermal(), default_pid())
    whole = floor(result.jitter_margin)
    fraction = result.jitter_margin - whole
    tilde = sqrt(whole * whole + 2 * whole * fraction + fraction)
    assert whole <= tilde < whole + 1


def _margin(jitter: float) -> Margins:
    """Return margins with only a jitter margin.

    Parameters
    ----------
    jitter
        Jitter margin in sample periods.

    Returns
    -------
    Margins
        Margins without a crossover.
    """
    return Margins(None, None, None, jitter)


def test_latency_verdict_inside_and_outside_the_margin() -> None:
    """Latencies below the margin are inside it, with the headroom in decades."""
    verdict = latency_verdict(_margin(400.0), [0.0002, 0.0004], PERIOD)
    assert verdict == {
        "largest_latency_periods": pytest.approx(0.4),
        "jitter_margin_periods": 400.0,
        "within_jitter_margin": True,
        "log10_headroom": pytest.approx(3.0),
    }
    outside = latency_verdict(_margin(0.5), [0.0008], PERIOD)
    assert outside["within_jitter_margin"] is False
    assert latency_verdict(_margin(1.0), [0.0], PERIOD)["log10_headroom"] is None


@pytest.mark.parametrize(
    ("latencies", "period"),
    [([], PERIOD), ([-1e-6], PERIOD), ([inf], PERIOD), ([nan], PERIOD), ([0.0], 0.0)],
)
def test_latency_verdict_refuses_invalid_input(latencies: list[float], period: float) -> None:
    """No latencies, a negative or non-finite latency, or no period is refused.

    Parameters
    ----------
    latencies
        Latencies in seconds.
    period
        Sample period in seconds.
    """
    with pytest.raises(ValueError, match="finite, non-negative latencies"):
        latency_verdict(_margin(1.0), latencies, period)
