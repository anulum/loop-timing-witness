# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original AMP platform admission tests

"""Exercise composed image/device resource admission on actual compiled topology."""

from __future__ import annotations

import pytest
from amp_platform import bind_platform
from test_amp_device import PATH
from test_amp_device import SELECTION as PLIC_SELECTION
from test_amp_device import SOURCE as DEVICE_SOURCE
from test_amp_memory import SELECTION as MEMORY_SELECTION
from test_amp_memory import SOURCE as MEMORY_SOURCE
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
MEMORY_BODY = MEMORY_SOURCE[MEMORY_SOURCE.index("    memory@") : MEMORY_SOURCE.rfind("};")]
SOURCE = DEVICE_SOURCE.replace("    soc {", MEMORY_BODY + "    soc {")


def test_complete_original_platform(compile_tree: CompileTree) -> None:
    """Bind firmware, telemetry, actual AXI and original machine context together.

    Parameters
    ----------
    compile_tree
        Actual compiler and public binary decoder.
    """
    platform = bind_platform(compile_tree(SOURCE), MEMORY_SELECTION, PATH, PLIC_SELECTION)
    assert platform.hart == 1
    assert platform.source == 40
    assert platform.memory.firmware.address == 0x80000000
    assert platform.memory.shared.address == 0x80080000
    assert platform.device.aperture.address == 0x40000000
    assert platform.device.plic.context == 2


@pytest.mark.parametrize(
    "extra",
    [
        'memory@c000000 { device_type = "memory"; reg = <0 0xc000000 0 0x1000>; };',
        "/memreserve/ 0xc000000 0x1000;",
    ],
)
def test_plic_memory_alias_refused(compile_tree: CompileTree, extra: str) -> None:
    """Refuse PLIC memory aliases even when firmware RAM and Witness AXI remain disjoint.

    Parameters
    ----------
    compile_tree
        Actual compiler and public decoder.
    extra
        Original conflicting RAM declaration or header reservation.
    """
    source = (
        SOURCE.replace("/dts-v1/;", "/dts-v1/; " + extra)
        if extra.startswith("/memreserve/")
        else SOURCE.replace("    soc {", extra + "    soc {")
    )
    with pytest.raises(ValueError, match="PLIC aperture intersects"):
        bind_platform(compile_tree(source), MEMORY_SELECTION, PATH, PLIC_SELECTION)
