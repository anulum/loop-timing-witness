# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Linux scheduling and run options

"""Exercise native Linux affinity and scheduler through actual process entry points."""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run
from test_native_uio_run import native_uio

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run", "native_uio"]


@pytest.mark.parametrize("policy", ["inherit", "cpu", "normal"])
def test_actual_policy(native_run: Path, tmp_path: Path, policy: str) -> None:
    """Check actual kernel policy metadata and preserve the parent scheduling state.

    Parameters
    ----------
    native_run
        Production native controller and RTL executable.
    tmp_path
        Exclusive run allocation.
    policy
        Inherited, single-CPU or explicit normal scheduler request.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    priority = os.sched_getparam(0).sched_priority
    cpu = min(affinity)
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    metadata = tmp_path / "native_metadata.json"
    options = [] if policy == "inherit" else ["--cpu", str(cpu)]
    if policy == "normal":
        options.extend(["--scheduler", "normal", "--priority", "0"])
    result = subprocess.run(
        [
            str(native_run),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "raw.csv"),
            "--metadata",
            str(metadata),
            *options,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    actual = json.loads(metadata.read_text())["host_policy"]
    assert actual["affinity_cpus"] == (sorted(affinity) if policy == "inherit" else [cpu])
    assert actual["scheduler"] == (os.SCHED_OTHER if policy == "normal" else scheduler)
    assert actual["priority"] == (0 if policy == "normal" else priority)
    assert actual["observed_cpu"] in actual["affinity_cpus"]
    assert actual["nice"] == os.getpriority(os.PRIO_PROCESS, 0)
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler
    assert os.sched_getparam(0).sched_priority == priority


@pytest.mark.parametrize(
    "options",
    [
        ["--cpu", "-1"],
        ["--cpu", "999999"],
        ["--cpu", "0tail"],
        ["--cpu"],
        ["--cpu", "0", "--cpu", "0"],
        ["--unknown", "0"],
        ["--scheduler", "rr"],
        ["--priority", "1"],
        ["--scheduler", "fifo"],
        ["--scheduler", "normal", "--priority", "1"],
        ["--scheduler", "fifo", "--cpu", "0", "--priority", "100"],
    ],
)
def test_refused_policy(native_run: Path, tmp_path: Path, options: list[str]) -> None:
    """Refuse malformed or unavailable policy before any original output is created.

    Parameters
    ----------
    native_run
        Actual production process entry.
    tmp_path
        Exclusive configuration and output allocation.
    options
        Deliberately invalid public command arguments.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), *options],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr
    assert not events.exists()
    assert not raw.exists()


def test_fifo_permissions(native_run: Path, tmp_path: Path) -> None:
    """Observe a real bounded FIFO run or the actual kernel permission refusal.

    Parameters
    ----------
    native_run
        Actual production process entry.
    tmp_path
        Exclusive configuration and run outputs.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    metadata = tmp_path / "native_metadata.json"
    cpu = min(os.sched_getaffinity(0))
    result = subprocess.run(
        [
            str(native_run),
            str(config),
            str(events),
            str(raw),
            "--metadata",
            str(metadata),
            "--cpu",
            str(cpu),
            "--scheduler",
            "fifo",
            "--priority",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        actual = json.loads(metadata.read_text())["host_policy"]
        assert actual["scheduler"] == os.SCHED_FIFO
        assert actual["priority"] == 1
        assert actual["affinity_cpus"] == [cpu]
    else:
        assert result.returncode == 1
        assert "cannot set Linux scheduler: Operation not permitted" in result.stderr
        assert not events.exists()
        assert not raw.exists()
        assert not metadata.exists()


@pytest.mark.parametrize("options", [["--cpu", "999999"], ["--scheduler", "fifo"]])
def test_uio_policy_refusal(native_uio: Path, tmp_path: Path, options: list[str]) -> None:
    """Exercise the same real policy refusal before unavailable UIO acquisition.

    Parameters
    ----------
    native_uio
        Actual Linux UIO executable.
    tmp_path
        Exclusive run allocation.
    options
        Outside-allowed CPU or incomplete FIFO policy.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [
            str(native_uio),
            str(config),
            str(events),
            str(raw),
            "uio4294967295",
            "witness",
            "1",
            "0",
            "0",
            *options,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert (
        "requested CPU is outside inherited affinity" in result.stderr
        or "FIFO requires explicit CPU and positive priority" in result.stderr
    )
    assert not events.exists()
    assert not raw.exists()
