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
from loop_timing_witness.host_profile import scaled


def _write_driver(directory: Path, captured: Path) -> Path:
    """Write a driver that runs the module command from the original and the captured tree.

    Parameters
    ----------
    directory
        Exclusive allocation; the captured command runs with it as working directory.
    captured
        Directory holding the captured package copy.

    Returns
    -------
    Path
        Driver script.
    """
    driver = directory / "commands.py"
    driver.write_text(
        "import os, subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'loop_timing_witness.validate_measurement_domain', "
        "'--help'], check=True)\n"
        "subprocess.run([sys.executable, '-m', 'loop_timing_witness.validate_measurement_domain', "
        f"'--help'], cwd={str(directory)!r}, "
        f"env={{**os.environ, 'PYTHONPATH': {str(captured)!r}}}, "
        "check=True)\n",
        encoding="utf-8",
    )
    return driver


def _measure(driver: Path, data_file: Path, parallel: Path) -> str:
    """Run the driver under the repository coverage settings and combine every data file.

    Parameters
    ----------
    driver
        Driver script.
    data_file
        Independent coverage data file.
    parallel
        Directory holding the subprocesses' parallel data files.

    Returns
    -------
    str
        The driver's standard output.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE"))
    }
    command = [sys.executable, "-m", "coverage"]
    rcfile = str(REPOSITORY_ROOT / "pyproject.toml")
    result = subprocess.run(
        [*command, "run", "--rcfile", rcfile, "--data-file", str(data_file), str(driver)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    subprocess.run(
        [*command, "combine", "--data-file", str(data_file), str(parallel)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=scaled(30),
    )
    return result.stdout


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
    driver = _write_driver(tmp_path, captured)
    data_file = tmp_path / "coverage-data"
    stdout = _measure(driver, data_file, tmp_path)
    # Python 3.14 and later name a module command by its -m invocation in the usage line.
    usage = "usage: python -m loop_timing_witness.validate_measurement_domain"
    assert stdout.count(usage) == 2
    data = CoverageData(basename=str(data_file))
    data.read()
    files = {Path(name).resolve() for name in data.measured_files()}
    original = REPOSITORY_ROOT / "src/loop_timing_witness/validate_measurement_domain.py"
    assert original in files
    assert data.lines(str(original))
    assert not any(path.is_relative_to(captured) for path in files)
