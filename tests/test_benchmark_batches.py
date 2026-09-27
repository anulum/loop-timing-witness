# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native batch validation and statistics tests

"""Refuse malformed actual benchmark batches through the public decoder."""

from __future__ import annotations

import pytest
from benchmark_batches import benchmark_statistics, decode_batch
from test_benchmark_controllers import native_batches

__all__ = ["native_batches"]


@pytest.mark.parametrize(
    "mutation", ["order", "missing", "extra", "count", "elapsed", "checksum", "number"]
)
def test_native_protocol_refusal(native_batches: list[str], mutation: str) -> None:
    """Refuse deliberate negative mutations of actual native batch output.

    Parameters
    ----------
    native_batches
        Real C and Rust stdout.
    mutation
        Deliberately invalid row field or order.
    """
    rows = native_batches[0].splitlines()
    fields = rows[0].split(",")
    if mutation == "order":
        rows.reverse()
    elif mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        fields.append("extra")
    else:
        index, value = {
            "count": (1, "1"),
            "elapsed": (2, "0"),
            "checksum": (3, "-1"),
            "number": (1, "abc"),
        }[mutation]
        fields[index] = value
    if mutation not in {"order", "missing"}:
        rows[0] = ",".join(fields)
    with pytest.raises(ValueError, match=r"native benchmark|invalid literal"):
        decode_batch("\n".join(rows))


def test_statistics_refusal(native_batches: list[str]) -> None:
    """Refuse too few real batches and deliberately invalid elapsed times.

    Parameters
    ----------
    native_batches
        Actual native process output.
    """
    elapsed = decode_batch(native_batches[0])[0][2]
    with pytest.raises(ValueError, match="positive"):
        benchmark_statistics([elapsed] * 4)
    with pytest.raises(ValueError, match="positive"):
        benchmark_statistics([elapsed] * 4 + [0])
