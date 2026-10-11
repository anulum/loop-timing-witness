# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — report transaction tests

"""Exercise complete and failed report writes on real filesystem paths."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from linux_load_trace_support import OwnedTrace
from report_outputs import write_report

from conftest import REPOSITORY_ROOT

MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]
RECORD_BYTES = 16


def create_concurrent_destination(target: Path, kind: str) -> int:
    """Create a real competing filesystem path and retain its original inode.

    Parameters
    ----------
    target
        Destination whose preservation is the report transaction contract.
    kind
        Directory, regular file or symbolic link to create.

    Returns
    -------
    int
        Actual inode of the competing path, without following a symlink.
    """
    if kind == "file":
        target.write_bytes(b"preserve")
    elif kind == "symlink":
        alternate = target.parent / "alternate"
        alternate.mkdir()
        (alternate / "sentinel").write_bytes(b"preserve")
        target.symlink_to(alternate, target_is_directory=True)
    else:
        target.mkdir()
        if kind == "nonempty":
            (target / "sentinel").write_bytes(b"preserve")
    return target.lstat().st_ino


@pytest.mark.parametrize("referent_exists", [False, True])
def test_existing_symlink_is_preserved(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path, *, referent_exists: bool
) -> None:
    """Refuse a preexisting symlink without publishing into its referent.

    Parameters
    ----------
    make_rtl_run
        Actual Icarus producer of the input run.
    run_tool
        Public source analyzer command runner.
    tmp_path
        Exclusive parent of the symlink and its referent.
    referent_exists
        Whether the symlink points to a real directory or an absent path.
    """
    run, _ = make_rtl_run()
    referent = tmp_path / "referent"
    if referent_exists:
        referent.mkdir()
    target = tmp_path / "existing-link"
    target.symlink_to(referent, target_is_directory=True)
    inode = target.lstat().st_ino
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(target))
    assert result.returncode == 1
    assert "report directory already exists" in result.stderr
    assert target.lstat().st_ino == inode
    assert target.readlink() == referent
    assert referent.exists() == referent_exists
    assert not list(tmp_path.glob(".existing-link.*"))
    assert not list(tmp_path.glob(".report-publication-probe.*"))


@pytest.mark.parametrize("kind", ["absent", "empty", "nonempty", "file", "symlink"])
def test_concurrent_destination_is_preserved(
    make_rtl_run: MakeRtlRun, tmp_path: Path, kind: str
) -> None:
    """Publish a complete report or preserve a real target created after staging.

    Parameters
    ----------
    make_rtl_run
        Real Icarus producer supplying validated report inputs.
    tmp_path
        Exclusive report parent, target and syscall log.
    kind
        Actual filesystem destination created by the concurrent actor.
    """
    run, _ = make_rtl_run()
    target = tmp_path / "racing-report"
    log = tmp_path / "publication.trace"
    process = subprocess.Popen(
        [
            "strace",
            "-f",
            "--kill-on-exit",
            "-o",
            str(log),
            "-e",
            "trace=rename,renameat,renameat2",
            "-e",
            "inject=renameat2:delay_enter=2s:when=2",
            sys.executable,
            str(REPOSITORY_ROOT / "tools/analyze_run.py"),
            str(run / "manifest.json"),
            "--output-dir",
            str(target),
        ],
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    owned = OwnedTrace(process, log, {process.pid: os.pidfd_open(process.pid)})
    try:
        deadline = time.monotonic() + 10
        staging = None
        while True:
            assert time.monotonic() < deadline, "actual completed staging was not observed in 10s"
            owned.observe()
            candidates = [
                path for path in tmp_path.glob(".racing-report.*") if str(path) in log.read_text()
            ]
            if candidates:
                staging = candidates[0]
                break
            assert process.poll() is None, "actual analyzer exited before staging observation"
            time.sleep(0.01)
        assert staging is not None, "actual completed staging was not observed"
        if kind == "absent":
            assert not target.exists()
            expected = {path.name: path.read_bytes() for path in staging.iterdir()}
            assert set(expected) == {
                "report.json",
                "interval_summary.csv",
                "jitter_summary.csv",
                "cycle_intervals.csv",
                "cycle_jitter.csv",
                "interval_p99.svg",
                "jitter_p99.svg",
                "energy_per_cycle.svg",
            }
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stdout + stderr
            assert {path.name: path.read_bytes() for path in target.iterdir()} == expected
            assert not list(tmp_path.glob(".racing-report.*"))
            assert "(DELAYED)" in log.read_text()
            return
        original_inode = create_concurrent_destination(target, kind)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 1, stdout + stderr
        assert target.lstat().st_ino == original_inode
        if kind == "file":
            assert target.read_bytes() == b"preserve"
        elif kind in {"nonempty", "symlink"}:
            assert (target / "sentinel").read_bytes() == b"preserve"
        else:
            assert not list(target.iterdir())
        assert not list(tmp_path.glob(".racing-report.*"))
        assert "(DELAYED)" in log.read_text()
    finally:
        owned.close()


def test_missing_output_parent_is_refused(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A report cannot silently create an unreviewed parent directory.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        Parent of the absent directory.
    """
    run, _ = make_rtl_run()
    output = tmp_path / "missing" / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert "report parent does not exist" in result.stderr
    assert not output.exists()


def test_interrupted_staging_is_removed(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A post-staging failure leaves no partial report or shadow directory.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        Report staging parent.
    """
    run, _ = make_rtl_run()
    completed = tmp_path / "complete"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(completed))
    assert result.returncode == 0, result.stderr
    report = json.loads((completed / "report.json").read_text(encoding="utf-8"))
    report["energy"]["per_rail"] = None
    target = tmp_path / "interrupted"
    with pytest.raises(TypeError):
        write_report(target, report, [])
    assert not target.exists()
    assert not list(tmp_path.glob(".interrupted.*"))


def test_empty_interval_plot_is_still_labelled(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A COMPUTE stream with no interval pairs yields a provenance-labelled chart.

    Parameters
    ----------
    make_rtl_run
        Icarus Verilog COMPUTE producer.
    run_tool
        Host command runner.
    tmp_path
        Report parent.
    """
    run, manifest = make_rtl_run("COMPUTE")
    original = (run / "events.bin").read_bytes()
    records = [
        original[offset : offset + RECORD_BYTES] for offset in range(0, len(original), RECORD_BYTES)
    ]
    data = b"".join(record for record in records if record[0] == 8)
    (run / "events.bin").write_bytes(data)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(data).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "compute-report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    svg = (output / "interval_p99.svg").read_text(encoding="utf-8")
    assert "simulation_only" in svg
    assert "99th percentile event intervals" in svg
