# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dense real matrices for the control-cost computation

"""Dense real matrices as lists of rows, with the operations the control cost uses.

A matrix is a list of equally long rows of floats. The operations are exact in their order of
evaluation, so a result is reproducible on any host with IEEE 754 doubles; none of them depends
on a numerical library. The exponential scales the matrix to a norm of at most 0.25, sums its
Taylor series and squares the result back; the solver is Gaussian elimination with partial
pivoting.
"""

from __future__ import annotations

from math import ceil, log2
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

type Matrix = list[list[float]]

_SCALED_NORM: Final = 0.25
"""Largest norm of the scaled matrix whose exponential the Taylor series sums."""

_TAYLOR_TERMS: Final = 30
"""Upper bound on the Taylor terms; at a norm of 0.25 twenty terms reach rounding."""


def expm(matrix: Matrix) -> Matrix:
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
    reduced = scaled(matrix, 2.0**-squarings)
    result = identity_matrix(len(matrix))
    term = identity_matrix(len(matrix))
    for order in range(1, _TAYLOR_TERMS + 1):
        term = scaled(mul(term, reduced), 1.0 / order)
        result = add(result, term)
        if max(abs(value) for row in term for value in row) == 0:
            break
    for _ in range(squarings):
        result = mul(result, result)
    return result


def solve(matrix: Matrix, right: list[float]) -> list[float]:
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


def identity_matrix(size: int) -> Matrix:
    """Return the identity matrix.

    Parameters
    ----------
    size
        Number of rows and columns.

    Returns
    -------
    Matrix
        The ``size`` by ``size`` identity.
    """
    return [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]


def zero_matrix(rows: int, columns: int) -> Matrix:
    """Return a zero matrix.

    Parameters
    ----------
    rows
        Number of rows.
    columns
        Number of columns.

    Returns
    -------
    Matrix
        The ``rows`` by ``columns`` zero matrix, each row its own list.
    """
    return [[0.0] * columns for _ in range(rows)]


def transpose(matrix: Matrix) -> Matrix:
    """Return the transpose.

    Parameters
    ----------
    matrix
        Matrix of any shape.

    Returns
    -------
    Matrix
        Its transpose.
    """
    return [list(column) for column in zip(*matrix, strict=True)]


def mul(left: Matrix, right: Matrix) -> Matrix:
    """Return the matrix product.

    Parameters
    ----------
    left
        Left factor.
    right
        Right factor with as many rows as ``left`` has columns.

    Returns
    -------
    Matrix
        ``left right``.
    """
    columns = transpose(right)
    return [
        [sum(x * y for x, y in zip(row, column, strict=True)) for column in columns] for row in left
    ]


def product(*factors: Matrix) -> Matrix:
    """Return the product of the factors from left to right.

    Parameters
    ----------
    *factors
        One or more matrices of chained shapes.

    Returns
    -------
    Matrix
        Their product; a single factor is returned as it is.
    """
    result = factors[0]
    for factor in factors[1:]:
        result = mul(result, factor)
    return result


def add(left: Matrix, right: Matrix) -> Matrix:
    """Return the matrix sum.

    Parameters
    ----------
    left
        First term.
    right
        Second term of the same shape.

    Returns
    -------
    Matrix
        ``left + right``.
    """
    return [[x + y for x, y in zip(a, b, strict=True)] for a, b in zip(left, right, strict=True)]


def scaled(matrix: Matrix, factor: float) -> Matrix:
    """Return the matrix times a scalar.

    Parameters
    ----------
    matrix
        Matrix of any shape.
    factor
        Scalar.

    Returns
    -------
    Matrix
        ``factor matrix``.
    """
    return [[factor * value for value in row] for row in matrix]


def symmetric(matrix: Matrix) -> Matrix:
    """Return the symmetric part, which removes rounding asymmetry.

    Parameters
    ----------
    matrix
        Square matrix.

    Returns
    -------
    Matrix
        ``(matrix + matrix') / 2``.
    """
    size = len(matrix)
    return [[(matrix[i][j] + matrix[j][i]) / 2 for j in range(size)] for i in range(size)]


def trace_product(left: Matrix, right: Matrix) -> float:
    """Return the trace of a product without forming the product.

    Parameters
    ----------
    left
        Left factor.
    right
        Right factor whose product with ``left`` is square.

    Returns
    -------
    float
        ``tr(left right)``.
    """
    return sum(left[i][j] * right[j][i] for i in range(len(left)) for j in range(len(right)))


def blocks(grid: Sequence[Sequence[Matrix]]) -> Matrix:
    """Assemble a block matrix from rows of equally sized square blocks.

    Parameters
    ----------
    grid
        Rows of blocks, every block of one order.

    Returns
    -------
    Matrix
        The assembled matrix.
    """
    return [
        [value for block in row for value in block[line]]
        for row in grid
        for line in range(len(row[0]))
    ]


def part(matrix: Matrix, row: int, column: int, order: int) -> Matrix:
    """Return one block of a matrix of equally sized square blocks.

    Parameters
    ----------
    matrix
        Block matrix.
    row
        Block row, from zero.
    column
        Block column, from zero.
    order
        Order of each block.

    Returns
    -------
    Matrix
        Block ``(row, column)``.
    """
    return [
        line[column * order : (column + 1) * order]
        for line in matrix[row * order : (row + 1) * order]
    ]


def embed(block: Matrix, size: int, *, identity: bool) -> Matrix:
    """Place a block in the top-left corner of the identity or the zero matrix.

    Parameters
    ----------
    block
        Block no larger than ``size`` in either dimension.
    size
        Order of the result.
    identity
        Embed in the identity when true, in the zero matrix otherwise.

    Returns
    -------
    Matrix
        The ``size`` by ``size`` matrix holding ``block`` at the top left.
    """
    result = identity_matrix(size) if identity else zero_matrix(size, size)
    for i, line in enumerate(block):
        result[i][: len(line)] = line
    return result
