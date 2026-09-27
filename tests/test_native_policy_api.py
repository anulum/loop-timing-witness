# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public Linux policy validation

"""Exercise public scheduling API options with actual child-only Linux policy changes."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT

__all__ = ["native_run"]


@pytest.fixture(scope="module")
def policy_program() -> Path:
    """Build the real Linux policy API corpus with strict warnings and gcov.

    Returns
    -------
    Path
        Native executable using actual libc scheduling and affinity syscalls.
    """
    directory = Path(
        os.environ.get("WITNESS_POLICY_BUILD_ROOT", str(REPOSITORY_ROOT / "build/policy_api"))
    )
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "policy_api_test"
    result = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "--coverage",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            str(REPOSITORY_ROOT / "tests/native/policy_api_test.cpp"),
            "-o",
            str(program),
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return program


@pytest.mark.parametrize(
    "scenario",
    [
        "cpu_low",
        "scheduler_low",
        "scheduler_high",
        "priority_low",
        "cpu_unavailable",
        "fifo_bounds",
        "fifo_no_cpu",
        "fifo_no_priority",
        "fifo_zero",
        "orphan_priority",
        "normal_priority",
        "power_config",
        "power_journal",
        "power_metadata",
        "preserve",
        "normal",
        "cpu_only",
        "normal_unpinned",
    ],
)
def test_actual_policy_api(policy_program: Path, scenario: str) -> None:
    """Keep real affinity and SCHED_BATCH intact after refusing malformed public requests.

    Parameters
    ----------
    policy_program
        Actual native public-policy API executable.
    scenario
        Invalid structure or valid inherited/explicit normal policy request.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    priority = os.sched_getparam(0).sched_priority
    result = subprocess.run(
        [str(policy_program), scenario], capture_output=True, text=True, check=False, timeout=5
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified {scenario}\n"
    assert result.stderr == ""
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler
    assert os.sched_getparam(0).sched_priority == priority


def test_inherited_batch_metadata(native_run: Path, tmp_path: Path) -> None:
    """Preserve actual inherited batch policy through a complete native run receipt.

    Parameters
    ----------
    native_run
        Production native run CLI linked to the actual selected RTL plant.
    tmp_path
        Exclusive configuration, real events/trace and receipt allocation.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none").replace("pid 32", "pid 2"), encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    affinity, scheduler = os.sched_getaffinity(0), os.sched_getscheduler(0)
    result = subprocess.run(
        [
            "chrt",
            "--batch",
            "0",
            str(native_run),
            str(config),
            str(events),
            str(raw),
            "--metadata",
            str(metadata),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    receipt = json.loads(metadata.read_text())
    policy = receipt["host_policy"]
    assert policy["scheduler"] == os.SCHED_BATCH
    assert policy["priority"] == 0
    assert policy["requested_scheduler"] == -1
    assert policy["affinity_cpus"] == sorted(affinity)
    assert receipt["result"]["samples"] == 2
    assert receipt["result"]["misses"] == 0
    assert events.stat().st_size == receipt["result"]["records"] * 16
    assert len(raw.read_text().splitlines()) == 3
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler
