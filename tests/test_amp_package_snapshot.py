# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — firmware custody of migrated verifier sources

"""Exercise captured Python package custody through the real firmware build commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_amp_image_flow import compile_tree, prepared_image

__all__ = ["compile_tree", "prepared_image"]
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative", ["amp_image_receipt.py", "data/run-manifest.schema.json", "py.typed"]
)
def test_firmware_refuses_changed_verifier_package(prepared_image: Path, relative: str) -> None:
    """Require original package bytes in the receipt and refuse their post-build alteration.

    Parameters
    ----------
    prepared_image
        Real RV64 firmware built and verified using the captured standalone Python package.
    relative
        Executable verifier module, schema or typing marker changed after successful compilation.
    """
    receipt = json.loads((prepared_image / "preparation.json").read_bytes())
    package = prepared_image / "source/tools/loop_timing_witness"
    for original in (ROOT / "src/loop_timing_witness").rglob("*"):
        if original.is_file() and (
            original.suffix in (".py", ".json") or original.name == "py.typed"
        ):
            retained = package / original.relative_to(ROOT / "src/loop_timing_witness")
            assert retained.read_bytes() == original.read_bytes()
            assert retained.relative_to(prepared_image).as_posix() in receipt["inputs"]
    changed = package / relative
    changed.write_bytes(changed.read_bytes() + b"\n")
    result = subprocess.run(
        ["make", "-C", str(prepared_image), "verify"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode != 0
    assert "AMP prepared source/input bytes or paths changed" in result.stderr
    assert "verify-inputs" in result.stderr
