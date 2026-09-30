# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual generated firmware image and original symbol admission tests

"""Build original whole RV64 firmware and verify compiled contracts and stack ownership."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from amp_contract import render_contract
from amp_elf_symbols import read_symbols
from amp_image_contract import admit_image_contract
from amp_platform import bind_platform
from test_amp_contract import RUN
from test_amp_device import PATH
from test_amp_device import SELECTION as PLIC_SELECTION
from test_amp_memory import SELECTION as MEMORY_SELECTION
from test_amp_platform import SOURCE
from test_device_tree_resources import CompileTree, compile_tree

if TYPE_CHECKING:
    from pathlib import Path

    from amp_platform import AmpPlatform

__all__ = ["compile_tree", "native_image"]


@pytest.fixture
def native_image(compile_tree: CompileTree, tmp_path: Path) -> tuple[bytes, AmpPlatform]:
    """Generate immutable inputs and compile all original controller/startup/exit sources.

    Parameters
    ----------
    compile_tree
        Actual original DTB compiler and decoder.
    tmp_path
        Exact owned firmware compilation directory.

    Returns
    -------
    tuple
        Original complete linked image and admitted original platform.
    """
    platform = bind_platform(compile_tree(SOURCE), MEMORY_SELECTION, PATH, PLIC_SELECTION)
    contract = tmp_path / "contract.c"
    contract.write_text(render_contract(platform, RUN), encoding="utf-8")
    compiler = os.environ.get("WITNESS_RV64_CC") or shutil.which("riscv64-linux-gnu-gcc")
    assert compiler is not None, "actual RV64 compiler is required"
    image = tmp_path / "firmware.elf"
    subprocess.run(
        [
            compiler,
            "-std=gnu11",
            "-O2",
            "-ffreestanding",
            "-fno-builtin",
            "-fno-pie",
            "-march=rv64imac_zicsr_zifencei",
            "-mabi=lp64",
            "-mcmodel=medany",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-Wstrict-prototypes",
            "-Wmissing-prototypes",
            "-nostdlib",
            "-nostartfiles",
            "-static",
            "-no-pie",
            "-Wl,--build-id=none",
            "-I.",
            "-Wl,--defsym=__witness_ram_origin=0x80000000",
            "-Wl,--defsym=__witness_ram_length=0x80000",
            "-Wl,--defsym=__witness_stack_size=16384",
            "-T",
            "runtime/bare_metal/firmware.ld",
            "runtime/bare_metal/entry.S",
            "runtime/bare_metal/amp_controller.c",
            "runtime/isa/amp_exit.c",
            "controllers/c/witness_controller.c",
            str(contract),
            "-o",
            str(image),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return image.read_bytes(), platform


def test_actual_full_firmware_contract(native_image: tuple[bytes, AmpPlatform]) -> None:
    """Admit original compiled readonly data, actual controller functions and writable stack.

    Parameters
    ----------
    native_image
        Actual complete target firmware and original platform.
    """
    content, platform = native_image
    segments = admit_image_contract(content, platform, RUN, 16384)
    symbols = read_symbols(content)
    assert symbols["witness_amp_platform"].size == 56
    assert symbols["witness_amp_run"].size == 60
    assert [segment.flags for segment in segments] == [5, 6]


@pytest.mark.parametrize("case", ["hart", "cycles", "stack"])
def test_input_image_mismatch(native_image: tuple[bytes, AmpPlatform], case: str) -> None:
    """Refuse original linked bytes when expected platform/run/stack inputs differ.

    Parameters
    ----------
    native_image
        Original whole compiled image and admitted platform.
    case
        Input whose expected immutable value differs.
    """
    content, platform = native_image
    run = RUN
    stack = 16384
    if case == "hart":
        platform = replace(platform, hart=2)
    elif case == "cycles":
        run = replace(RUN, cycles=11)
    else:
        stack = 8192
    with pytest.raises(ValueError, match=r"bytes differ|stack geometry"):
        admit_image_contract(content, platform, run, stack)
