# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — default discrete Riccati gains and quantized stability

"""Check the published default design against its Riccati and steady-state equations."""

from __future__ import annotations

import math

import pytest

SCALE = 1 << 24


def reference_dare(
    matrix: tuple[tuple[float, ...], ...],
    vector: tuple[float, ...],
    weights: tuple[float, ...],
) -> tuple[list[float], list[list[float]]]:
    """Solve the textbook finite-horizon recurrence to a checked stationary limit.

    Parameters
    ----------
    matrix
        Actual quantized plant transition matrix in real units.
    vector
        Actual quantized plant input vector.
    weights
        Diagonal state cost; the input cost is one.

    Returns
    -------
    tuple
        Stationary state-feedback gains and positive Riccati matrix.
    """
    size = len(vector)
    cost = [[weights[i] if i == j else 0.0 for j in range(size)] for i in range(size)]
    riccati = [row[:] for row in cost]
    for _ in range(20000):
        p_input = [sum(riccati[i][j] * vector[j] for j in range(size)) for i in range(size)]
        denominator = 1.0 + sum(vector[i] * p_input[i] for i in range(size))
        p_matrix = [
            [sum(riccati[i][k] * matrix[k][j] for k in range(size)) for j in range(size)]
            for i in range(size)
        ]
        gains = [
            sum(vector[i] * p_matrix[i][j] for i in range(size)) / denominator for j in range(size)
        ]
        following = [
            [
                cost[i][j]
                + sum(matrix[h][i] * p_matrix[h][j] for h in range(size))
                - sum(matrix[h][i] * p_input[h] for h in range(size)) * gains[j]
                for j in range(size)
            ]
            for i in range(size)
        ]
        residual = max(
            abs(following[i][j] - riccati[i][j]) for i in range(size) for j in range(size)
        )
        riccati = following
        if residual < 1e-10:
            return gains, riccati
    pytest.fail("default discrete Riccati recurrence did not converge")


def test_default_mechanical_riccati_and_quantized_stability() -> None:
    """The gains used by real feedback tests satisfy the documented mechanical design."""
    matrix = ((16777208 / SCALE, 16769 / SCALE), (-16769 / SCALE, 16760439 / SCALE))
    vector = (8 / SCALE, 16769 / SCALE)
    gains, riccati = reference_dare(matrix, vector, (10.0, 1.0))
    assert [round(gain * SCALE) for gain in gains] == [38822697, 26419076]
    assert riccati[0][0] > 0
    assert riccati[0][0] * riccati[1][1] - riccati[0][1] * riccati[1][0] > 0
    closed = [
        [matrix[i][j] - vector[i] * ([38822697, 26419076][j] / SCALE) for j in range(2)]
        for i in range(2)
    ]
    trace = closed[0][0] + closed[1][1]
    determinant = closed[0][0] * closed[1][1] - closed[0][1] * closed[1][0]
    assert 1 - determinant > 0
    assert 1 - trace + determinant > 0
    assert 1 + trace + determinant > 0
    inverse_det = (1 - closed[0][0]) * (1 - closed[1][1]) - closed[0][1] * closed[1][0]
    steady_gain = ((1 - closed[1][1]) * vector[0] + closed[0][1] * vector[1]) / inverse_det
    assert round(SCALE / steady_gain) == 55599913


def test_default_thermal_against_independent_quadratic_solution() -> None:
    """The scalar gain agrees with a closed-form positive Riccati root."""
    transition = 16760447 / SCALE
    input_gain = 16769 / SCALE
    gains, riccati = reference_dare(((transition,),), (input_gain,), (1.0,))
    linear = 1 - transition**2 - input_gain**2
    positive_root = 2 / (linear + math.sqrt(linear**2 + 4 * input_gain**2))
    assert math.isclose(riccati[0][0], positive_root, rel_tol=1e-9)
    independent_gain = input_gain * positive_root * transition / (1 + input_gain**2 * positive_root)
    assert round(independent_gain * SCALE) == round(gains[0] * SCALE) == 6944437
    closed = transition - input_gain * (6944437 / SCALE)
    assert abs(closed) < 1
    assert round((1 - closed) / input_gain * SCALE) == 23721653
