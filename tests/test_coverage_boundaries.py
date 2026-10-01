# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — canonical coverage and captured package boundaries

"""Keep independent firmware package snapshots out of canonical source totals."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from coverage import CoverageData

from conftest import REPOSITORY_ROOT


def test_canonical_and_snapshot_commands_have_distinct_coverage(tmp_path: Path) -> None:
    """Run both real module commands and measure only the original source tree.

    Parameters
    ----------
    tmp_path
        Exclusive captured package, subprocess driver and independent coverage data.
    """
    captured = tmp_path / "source" / "tools"
    captured.mkdir(parents=True)
    shutil.copytree(
        REPOSITORY_ROOT / "src" / "loop_timing_witness",
        captured / "loop_timing_witness",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    driver = tmp_path / "commands.py"
    driver.write_text(
        "import os, subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'loop_timing_witness.validate_measurement_domain', "
        "'--help'], check=True)\n"
        "subprocess.run([sys.executable, '-m', 'loop_timing_witness.validate_measurement_domain', "
        f"'--help'], cwd={str(tmp_path)!r}, env={{**os.environ, 'PYTHONPATH': {str(captured)!r}}}, "
        "check=True)\n",
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE"))
    }
    data_file = tmp_path / "coverage-data"
    command = [sys.executable, "-m", "coverage"]
    result = subprocess.run(
        [
            *command,
            "run",
            "--rcfile",
            str(REPOSITORY_ROOT / "pyproject.toml"),
            "--data-file",
            str(data_file),
            str(driver),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("usage: validate_measurement_domain.py") == 2
    subprocess.run(
        [*command, "combine", "--data-file", str(data_file), str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    data = CoverageData(basename=str(data_file))
    data.read()
    files = {Path(name).resolve() for name in data.measured_files()}
    original = REPOSITORY_ROOT / "src/loop_timing_witness/validate_measurement_domain.py"
    assert original in files
    assert data.lines(str(original))
    assert not any(path.is_relative_to(captured) for path in files)
