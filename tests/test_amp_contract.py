# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable contract generation and actual C ABI admission

"""Compile generated native resource contracts and exercise raw run input refusals."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from amp_contract import AmpRun, render_contract
from amp_platform import bind_platform
from test_amp_device import PATH
from test_amp_device import SELECTION as PLIC_SELECTION
from test_amp_memory import SELECTION as MEMORY_SELECTION
from test_amp_platform import SOURCE
from test_device_tree_resources import CompileTree, compile_tree

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["compile_tree"]
COEFFICIENTS = (1, 2, 16777216, 3, -4, 5, 6, -2147483648, 2147483647, -8, 9)
RUN = AmpRun(10, 32768, 0, 0, COEFFICIENTS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cycles", 0),
        ("cycles", True),
        ("cycles", -1),
        ("cycles", 1 << 32),
        ("period_ticks", 0),
        ("period_ticks", 1 << 32),
        ("lqr", 2),
        ("overload_iterations", 10000001),
    ],
)
def test_invalid_native_scalars(field: str, value: int) -> None:
    """Refuse raw fields outside the original native integer and runtime bounds.

    Parameters
    ----------
    field
        Exact run scalar field.
    value
        Invalid field value.
    """
    values = {
        "cycles": RUN.cycles,
        "period_ticks": RUN.period_ticks,
        "lqr": RUN.lqr,
        "overload_iterations": RUN.overload_iterations,
    }
    values[field] = value
    with pytest.raises(ValueError, match="native integer"):
        AmpRun(**values, coefficients=COEFFICIENTS)


@pytest.mark.parametrize(
    ("index", "value"),
    [
        (0, -1),
        (1, -1),
        (2, -1),
        (2, 16777217),
        (3, -1),
        (7, 1),
        (8, -1),
        (9, 1),
        (10, -1),
        (4, True),
        (4, 1 << 31),
    ],
)
def test_invalid_native_coefficients(index: int, value: int) -> None:
    """Refuse invalid bounds and gains while allowing signed LQR coefficients.

    Parameters
    ----------
    index
        Original declaration-order coefficient index.
    value
        Invalid coefficient replacement.
    """
    values = list(COEFFICIENTS)
    values[index] = value
    with pytest.raises(ValueError, match="native"):
        replace(RUN, coefficients=tuple(values))


def test_coefficient_geometry_and_timer() -> None:
    """Refuse incomplete coefficient words and duration overflow before compilation."""
    with pytest.raises(ValueError, match="native integer"):
        replace(RUN, coefficients=COEFFICIENTS[:-1])
    with pytest.raises(ValueError, match="native integer"):
        replace(RUN, cycles=(1 << 32) - 1, period_ticks=(1 << 32) - 1)


@pytest.mark.parametrize("capacity", [65536, 4096])
def test_actual_compiled_mailbox_capacity(
    compile_tree: CompileTree, tmp_path: Path, capacity: int
) -> None:
    """Check real compiler sizeof against RAM independently of the caller minimum.

    Parameters
    ----------
    compile_tree
        Actual DTB compiler and public decoder.
    tmp_path
        Exact owned generated C and object paths.
    capacity
        Original telemetry reservation to admit or refuse during real C compilation.
    """
    source = SOURCE.replace("0x80080000 0 0x10000", f"0x80080000 0 {capacity}")
    selection = replace(MEMORY_SELECTION, mailbox_bytes=32)
    platform = bind_platform(compile_tree(source), selection, PATH, PLIC_SELECTION)
    contract = tmp_path / "contract.c"
    contract.write_text(render_contract(platform, RUN), encoding="utf-8")
    compiler = os.environ.get("WITNESS_RV64_CC") or shutil.which("riscv64-linux-gnu-gcc")
    assert compiler is not None, "actual RV64 compiler is required"
    result = subprocess.run(
        [
            compiler,
            "-std=gnu11",
            "-ffreestanding",
            "-march=rv64imac_zicsr_zifencei",
            "-mabi=lp64",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-I.",
            "-c",
            str(contract),
            "-o",
            str(tmp_path / "contract.o"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if capacity == 4096:
        assert result.returncode != 0
        assert "actual telemetry ABI exceeds reserved memory" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "contract.o").stat().st_size > 0
