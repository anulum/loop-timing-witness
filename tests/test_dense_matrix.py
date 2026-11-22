# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dense real matrices for the control-cost computation

"""Check every dense-matrix operation against values known in closed form."""

from __future__ import annotations

from math import cos, exp, isclose, pi, sin

from loop_timing_witness.dense_matrix import (
    add,
    blocks,
    embed,
    expm,
    identity_matrix,
    mul,
    part,
    product,
    scaled,
    solve,
    symmetric,
    trace_product,
    transpose,
    zero_matrix,
)


def _close(left: list[list[float]], right: list[list[float]], tolerance: float) -> bool:
    """Tell whether two matrices agree entry by entry within an absolute tolerance."""
    return len(left) == len(right) and all(
        len(a) == len(b) and all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))
        for a, b in zip(left, right, strict=True)
    )


def test_identity_and_zero_matrices_have_independent_rows() -> None:
    """Each row is its own list, so writing one entry changes only that entry."""
    unit, zero = identity_matrix(3), zero_matrix(2, 3)
    assert unit == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert zero == [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    zero[0][1] = 5.0
    assert zero == [[0.0, 5.0, 0.0], [0.0, 0.0, 0.0]]


def test_rectangular_products_follow_the_row_by_column_rule() -> None:
    """Transpose, product and chained product of non-square factors."""
    left = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    right = [[7.0, 8.0], [9.0, 10.0], [11.0, 12.0]]
    assert transpose(left) == [[1.0, 4.0], [2.0, 5.0], [3.0, 6.0]]
    assert mul(left, right) == [[58.0, 64.0], [139.0, 154.0]]
    assert product(left) is left
    assert product(left, right, [[1.0], [-1.0]]) == [[-6.0], [-15.0]]


def test_sum_scale_symmetric_part_and_trace_of_a_product() -> None:
    """Entry-wise operations and the trace of a product formed without the product."""
    left = [[1.0, 2.0], [3.0, 4.0]]
    right = [[0.5, -1.0], [2.0, 0.25]]
    assert add(left, right) == [[1.5, 1.0], [5.0, 4.25]]
    assert scaled(left, -2.0) == [[-2.0, -4.0], [-6.0, -8.0]]
    assert symmetric(left) == [[1.0, 2.5], [2.5, 4.0]]
    whole = mul(left, right)
    assert trace_product(left, right) == whole[0][0] + whole[1][1] == 2.5
    wide, tall = [[1.0, 2.0, 3.0]], [[4.0], [5.0], [6.0]]
    assert trace_product(wide, tall) == 32.0


def test_blocks_assemble_and_parts_return_each_block() -> None:
    """A two-by-two grid of order-two blocks round-trips through ``part``."""
    grid = [
        [[[1.0, 2.0], [3.0, 4.0]], [[5.0, 6.0], [7.0, 8.0]]],
        [[[9.0, 10.0], [11.0, 12.0]], [[13.0, 14.0], [15.0, 16.0]]],
    ]
    whole = blocks(grid)
    assert whole == [
        [1.0, 2.0, 5.0, 6.0],
        [3.0, 4.0, 7.0, 8.0],
        [9.0, 10.0, 13.0, 14.0],
        [11.0, 12.0, 15.0, 16.0],
    ]
    for row in range(2):
        for column in range(2):
            assert part(whole, row, column, 2) == grid[row][column]


def test_embedding_places_a_block_in_the_identity_or_the_zero_matrix() -> None:
    """The block fills the top-left corner; the rest is the identity or zero."""
    block = [[2.0, 3.0], [4.0, 5.0]]
    assert embed(block, 3, identity=True) == [[2.0, 3.0, 0.0], [4.0, 5.0, 0.0], [0.0, 0.0, 1.0]]
    assert embed(block, 3, identity=False) == [[2.0, 3.0, 0.0], [4.0, 5.0, 0.0], [0.0, 0.0, 0.0]]
    assert embed([[7.0]], 2, identity=True) == [[7.0, 0.0], [0.0, 1.0]]


def test_exponentials_known_in_closed_form() -> None:
    """Zero, nilpotent, diagonal and rotation generators, with and without scaling."""
    assert expm(zero_matrix(2, 2)) == identity_matrix(2)
    # A nilpotent generator ends its series after two terms, exactly.
    assert expm([[0.0, 0.2], [0.0, 0.0]]) == [[1.0, 0.2], [0.0, 1.0]]
    small = expm([[0.1, 0.0], [0.0, -0.2]])
    assert isclose(small[0][0], exp(0.1), rel_tol=1e-15)
    assert isclose(small[1][1], exp(-0.2), rel_tol=1e-15)
    assert small[0][1] == small[1][0] == 0.0
    # A norm of 12 is scaled by 2**-6 and squared back six times.
    large = expm([[12.0, 0.0], [0.0, -3.0]])
    assert isclose(large[0][0], exp(12.0), rel_tol=1e-13)
    assert isclose(large[1][1], exp(-3.0), rel_tol=1e-13)
    angle = pi / 3
    rotation = expm([[0.0, -angle], [angle, 0.0]])
    assert _close(rotation, [[cos(angle), -sin(angle)], [sin(angle), cos(angle)]], 1e-15)


def test_exponential_of_a_non_normal_matrix_inverts_its_negative() -> None:
    """``e^A e^-A`` is the identity for a matrix that needs scaling."""
    generator = [[0.3, 2.0, 0.0], [0.0, -0.7, 1.5], [0.4, 0.0, 0.1]]
    assert _close(mul(expm(generator), expm(scaled(generator, -1.0))), identity_matrix(3), 1e-13)


def test_solving_swaps_rows_for_a_zero_pivot_and_keeps_the_matrix() -> None:
    """A zero leading entry forces a row exchange; a zero below a pivot needs no elimination."""
    matrix = [[0.0, 2.0, 1.0], [1.0, 1.0, 0.0], [0.0, 1.0, 3.0]]
    original = [list(row) for row in matrix]
    solution = solve(matrix, [5.0, 3.0, 10.0])
    assert _close([solution], [[2.0, 1.0, 3.0]], 1e-14)
    assert matrix == original
    residual = [sum(a * x for a, x in zip(row, solution, strict=True)) for row in matrix]
    assert _close([residual], [[5.0, 3.0, 10.0]], 1e-14)
