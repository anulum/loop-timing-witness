# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual firmware CLI entry and literal recipe refusal tests

"""Exercise real CLI processes and refuse unsafe literal Make argument geometry."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from amp_image_options import verification_arguments
from prepare_amp_image import BuildInputs, prepare_image
from test_amp_image_flow import CONFIGURATION, REQUEST, ROOT, prepared_image
from test_amp_platform import SOURCE
from test_device_tree_resources import CompileTree, compile_tree

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["compile_tree", "prepared_image"]


def test_public_cli_refusals(prepared_image: Path) -> None:
    """Exercise actual process entry points for exclusive preparation and verified original images.

    Parameters
    ----------
    prepared_image
        Original actual image build.
    """
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(prepared_image / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(prepared_image / "configuration.txt")
    compiler = os.environ.get("WITNESS_RV64_CC")
    assert compiler is not None
    preparation = subprocess.run(
        [
            sys.executable,
            "tools/prepare_amp_image.py",
            *arguments,
            "--output",
            str(prepared_image),
            "--compiler",
            compiler,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert preparation.returncode == 1
    assert "FAIL" in preparation.stderr
    verification = subprocess.run(
        [
            sys.executable,
            "tools/verify_amp_image.py",
            "--directory",
            str(prepared_image),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert verification.returncode == 0, verification.stderr


def test_line_separator_compiler_refused(compile_tree: CompileTree, tmp_path: Path) -> None:
    """Refuse a literal executable filename that cannot fit a single generated Make recipe.

    Parameters
    ----------
    compile_tree
        Actual original dtc compiler.
    tmp_path
        Exact owned staging for a negative argument admission case.
    """
    compile_tree(SOURCE)
    config = tmp_path / "config.txt"
    config.write_bytes(CONFIGURATION)
    compiler = tmp_path / "compiler\nname"
    shutil.copyfile("/usr/bin/true", compiler)
    compiler.chmod(0o700)
    build = BuildInputs(ROOT, tmp_path / "platform.dtb", config, compiler, isa=False)
    with pytest.raises(ValueError, match="line separators"):
        prepare_image(build, tmp_path / "image", REQUEST)
