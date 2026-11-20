# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — float64 reference of the benchmark control loops

"""Check the float64 reference against the documented design values and its own rules."""

from __future__ import annotations

from math import exp

import pytest

from loop_timing_witness.control_reference import (
    SCALE,
    Lqr,
    Plant,
    Sample,
    closed_loop,
    default_pid,
    deviation,
    lqr,
    mechanical_plant,
    steady_period,
    thermal_plant,
)


def _raw(value: float) -> int:
    """Return a real value in raw Q8.24 units, rounded to nearest with ties to even.

    Parameters
    ----------
    value
        Real value.

    Returns
    -------
    int
        Raw value.
    """
    return round(value * SCALE)


def test_plants_round_to_the_documented_raw_coefficients() -> None:
    """Both discretizations round to the raw table of the plant witness document."""
    mechanical, thermal = mechanical_plant(), thermal_plant()
    assert [_raw(value) for row in mechanical.transition for value in row] == [
        16777208,
        16769,
        -16769,
        16760439,
    ]
    assert [_raw(value) for value in mechanical.input] == [8, 16769]
    assert [_raw(value) for value in thermal.transition[0]] == [16760447]
    assert [_raw(value) for value in thermal.input] == [16769]


@pytest.mark.parametrize(
    "parameters", [(0.0, 1.0, 1.0, 1.0), (0.001, 1.0, 3.0, 1.0), (0.001, -1.0, 1.0, 1.0)]
)
def test_mechanical_plant_refuses_other_models(parameters: tuple[float, ...]) -> None:
    """A zero period, an overdamped model or a negative mass is refused.

    Parameters
    ----------
    parameters
        Period, mass, damping and stiffness.
    """
    with pytest.raises(ValueError, match="positive, underdamped"):
        mechanical_plant(*parameters)


def test_thermal_plant_refuses_nonpositive_parameters() -> None:
    """A zero time constant is refused."""
    with pytest.raises(ValueError, match="positive parameters"):
        thermal_plant(tau=0.0)


def test_default_pid_rounds_to_the_documented_raw_gains() -> None:
    """The unquantized PID rounds to the raw defaults of the controller document."""
    pid = default_pid()
    assert [_raw(value) for value in (pid.kp, pid.ki_period, pid.decay, pid.derivative_gain)] == [
        33554432,
        16777,
        8388608,
        4194304,
    ]
    assert (pid.output_min, pid.output_max, pid.integral_min, pid.integral_max) == (-4, 4, -2, 2)


def test_lqr_on_the_quantized_plants_gives_the_documented_gains() -> None:
    """The documented gains are the design on the quantized plants, rounded to raw units."""
    quantized = Plant(
        ((16777208 / SCALE, 16769 / SCALE), (-16769 / SCALE, 16760439 / SCALE)),
        (8 / SCALE, 16769 / SCALE),
    )
    mechanical = lqr(quantized, (10.0, 1.0))
    assert [_raw(mechanical.kx), _raw(mechanical.kv), _raw(mechanical.nr)] == [
        38822697,
        26419076,
        55599913,
    ]
    thermal = lqr(Plant(((16760447 / SCALE,),), (16769 / SCALE,)), (1.0,))
    assert [_raw(thermal.kx), _raw(thermal.kv), _raw(thermal.nr)] == [6944437, 0, 23721653]
    assert (thermal.output_min, thermal.output_max) == (-4.0, 4.0)


@pytest.mark.parametrize(
    ("weights", "input_weight"), [((1.0,), 1.0), ((10.0, 0.0), 1.0), ((10.0, 1.0), 0.0)]
)
def test_lqr_refuses_mismatched_or_nonpositive_weights(
    weights: tuple[float, ...], input_weight: float
) -> None:
    """Weights must match the plant's states and be positive.

    Parameters
    ----------
    weights
        State weights.
    input_weight
        Input weight.
    """
    with pytest.raises(ValueError, match="one positive weight per state"):
        lqr(mechanical_plant(), weights, input_weight)


def test_lqr_refuses_an_uncontrollable_unstable_plant() -> None:
    """An unstable pole that the input cannot reach has no stationary solution."""
    with pytest.raises(ValueError, match="did not converge"):
        lqr(Plant(((1.1,),), (0.0,)), (1.0,))


@pytest.mark.parametrize("model", ["mechanical", "thermal"])
def test_float_loops_settle_on_the_reference(model: str) -> None:
    """Every unsaturated float64 loop settles on a unit reference with a unit command.

    Parameters
    ----------
    model
        Plant model.
    """
    thermal = model == "thermal"
    plant = thermal_plant() if thermal else mechanical_plant()
    for controller in (default_pid(), lqr(plant, (1.0,) if thermal else (10.0, 1.0))):
        final = closed_loop(plant, controller, 1.0, 64000)[-1]
        assert final.output == pytest.approx(1.0, abs=1e-6)
        assert final.command == pytest.approx(1.0, abs=1e-6)
        assert final.velocity == pytest.approx(0.0, abs=1e-6)


def test_first_sample_is_at_rest_and_pid_has_no_derivative_kick() -> None:
    """The plant starts at rest; the first PID command is proportional plus integral."""
    first = closed_loop(mechanical_plant(), default_pid(), 1.0, 1)
    assert first == [Sample(0.0, 0.0, 2.0 + 0.001)]


@pytest.mark.parametrize("reference", [10.0, -10.0])
def test_saturated_pid_holds_its_integral(reference: float) -> None:
    """A reference beyond the actuator range saturates the command and holds the integral.

    Parameters
    ----------
    reference
        Unreachable reference of either sign.
    """
    trajectory = closed_loop(thermal_plant(), default_pid(), reference, 2000)
    sign = 1.0 if reference > 0 else -1.0
    assert all(sample.command == 4.0 * sign for sample in trajectory)
    assert trajectory[-1].output == pytest.approx(4.0 * sign * (1 - exp(-0.001) ** 1999))


def test_saturated_lqr_clamps_its_command() -> None:
    """An LQR command beyond the bounds is clamped."""
    controller = Lqr(1.0, 0.0, 100.0, -4.0, 4.0)
    assert closed_loop(thermal_plant(), controller, 1.0, 3)[0].command == 4.0


def test_closed_loop_refuses_no_samples() -> None:
    """A loop of no samples is refused."""
    with pytest.raises(ValueError, match="at least one sample"):
        closed_loop(thermal_plant(), default_pid(), 1.0, 0)


def test_steady_period_finds_fixed_points_and_cycles() -> None:
    """The first repeated state gives the period and the start of the cycle."""
    assert steady_period([(0,), (1,), (2,), (2,)], 4) == (1, 2)
    assert steady_period([(5,), (1,), (2,), (1,), (2,)], 10) == (2, 1)
    assert steady_period([(9,), (1,), (2,), (1,)], 3) == (2, 1)


def test_steady_period_refuses_a_tail_without_repetition() -> None:
    """A tail of distinct states is refused."""
    with pytest.raises(ValueError, match="no state repeats within the last 3 samples"):
        steady_period([(1,), (2,), (3,)], 3)


def test_deviation_reports_the_largest_differences() -> None:
    """The largest absolute output and command differences are reported."""
    fixed = [Sample(1.0, 0.0, 2.0), Sample(0.5, 0.0, -1.0)]
    reference = [Sample(1.25, 9.0, 2.0), Sample(0.5, 0.0, 1.0)]
    assert deviation(fixed, reference) == {"output": 0.25, "command": 2.0}


@pytest.mark.parametrize(("fixed", "reference"), [([], []), ([Sample(0.0, 0.0, 0.0)], [])])
def test_deviation_refuses_empty_or_unequal_trajectories(
    fixed: list[Sample], reference: list[Sample]
) -> None:
    """Empty or unequal trajectories are refused.

    Parameters
    ----------
    fixed, reference
        Trajectories.
    """
    with pytest.raises(ValueError, match="equal length"):
        deviation(fixed, reference)
