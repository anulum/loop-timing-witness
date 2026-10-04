# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — coverage export through real collected data and public entry points

"""Verify coverage export identity, counts and the unchanged complete-coverage gate."""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from coverage import Coverage
from export_python_coverage import main

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def test_complete_real_policy_profile_exports_repository_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real public guard cases produce a complete profile accepted by the exporter."""
    data = tmp_path / "profile"
    environment = dict(os.environ, COVERAGE_FILE=str(data))
    subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "-m",
            "pytest",
            "-q",
            "tests/test_workflow_publication.py",
            "-k",
            "not coverage_report_binding",
            "--cov=workflow_publication",
            "--cov-branch",
            "--cov-report=",
            "--cov-fail-under=100",
            f"--basetemp={tmp_path / 'policy-cases'}",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("COVERAGE_FILE", str(data))
    output = tmp_path / "coverage.xml"
    assert main([str(output)]) == 0
    filenames = set(re.findall(r'<class [^>]*filename="([^"]+)"', output.read_text()))
    assert filenames == {"tools/workflow_publication.py"}
    monkeypatch.setattr(sys, "argv", ["export_python_coverage.py", str(output)])
    with pytest.raises(SystemExit) as completed:
        runpy.run_path(
            str(REPOSITORY_ROOT / "tools/export_python_coverage.py"), run_name="__main__"
        )
    assert completed.value.code == 0


def test_original_source_profile_keeps_duplicate_basenames_and_refuses_incomplete_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An actual firmware-preparation CLI profile preserves every file and counter.

    This profile deliberately contains partial execution, including both original
    dependency modules with the same basename. Exporting cannot turn it green.
    """
    data = tmp_path / "profile"
    subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "-m",
            "coverage",
            "run",
            f"--data-file={data}",
            "tools/prepare_amp_image.py",
            "--help",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    collected = Coverage(data_file=str(data), config_file="pyproject.toml")
    collected.combine()
    collected.save()
    collected.get_data().close()
    monkeypatch.setenv("COVERAGE_FILE", str(data))
    original = Coverage(config_file="pyproject.toml")
    original.load()
    loaded = original.get_data()
    before = tmp_path / "original.json"
    original.json_report(outfile=str(before))
    baseline = json.loads(before.read_text())
    output = tmp_path / "coverage.xml"
    assert main([str(output)]) == 1
    # Inspect only the trusted XML serialised by this actual exporter run.
    xml = output.read_text()
    attributes = xml.split("<coverage ", 1)[1].split(">", 1)[0]
    totals = dict(re.findall(r'([a-z-]+)="([0-9]+)"', attributes))
    filenames = re.findall(r'<class [^>]*filename="([^"]+)"', xml)
    assert len(filenames) == len(set(filenames)) == len(baseline["files"])
    assert set(filenames) == set(baseline["files"])
    assert "tools/amp_image_dependencies.py" in filenames
    assert "src/loop_timing_witness/amp_image_dependencies.py" in filenames
    assert int(totals["lines-valid"]) == baseline["totals"]["num_statements"]
    assert int(totals["lines-covered"]) == baseline["totals"]["covered_lines"]
    assert int(totals["branches-valid"]) == baseline["totals"]["num_branches"]
    assert int(totals["branches-covered"]) == baseline["totals"]["covered_branches"]
    assert xml.count("<line ") == int(totals["lines-valid"])
    unchanged = Coverage(data_file=str(data))
    unchanged.load()
    try:
        assert original.get_data().measured_files() == unchanged.get_data().measured_files()
    finally:
        # Reporting replaced the loaded data by a remapped in-memory copy.
        loaded.close()
        original.get_data().close(force=True)
        unchanged.get_data().close()
