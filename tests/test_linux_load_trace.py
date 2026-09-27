# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual kernel policy interference and receipt corruption

"""Exercise real guard failures while syscalls retain their actual kernel results."""

from __future__ import annotations

import hashlib
import json
import os
import select
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from linux_load_trace_support import trace_command
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from typing import Any

    from linux_load_trace_support import OwnedTrace

__all__ = ["native_run"]


def test_actual_policy_readback_mismatch(tmp_path: Path) -> None:
    """Change an owned worker scheduler before its real kernel readback.

    Parameters
    ----------
    tmp_path
        Exclusive worker and syscall trace allocation.
    """
    policy = os.sched_getscheduler(0)
    affinity = os.sched_getaffinity(0)
    workspace = tmp_path / "worker"
    workspace.mkdir()
    with trace_command(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load_worker.py"),
            "idle",
            str(min(affinity)),
            "4096",
            str(workspace),
        ],
        "sched_getscheduler:delay_enter=2s:when=1",
        tmp_path / "policy.strace",
    ) as trace:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            trace.observe()
            if trace.log.exists() and "sched_setaffinity" in trace.log.read_text():
                break
            assert trace.process.poll() is None
            time.sleep(0.005)
        else:
            pytest.fail("actual worker affinity syscall was not observed")
        children = (
            Path(f"/proc/{trace.process.pid}/task/{trace.process.pid}/children").read_text().split()
        )
        assert len(children) == 1
        worker = int(children[0])
        trace.observe()
        assert worker in trace.descriptors
        assert not select.select([trace.descriptors[worker]], [], [], 0)[0]
        assert b"linux_load_worker.py" in Path(f"/proc/{worker}/cmdline").read_bytes()
        os.sched_setscheduler(worker, os.SCHED_BATCH, os.sched_param(0))
        assert os.sched_getscheduler(worker) == os.SCHED_BATCH
        stdout, stderr = trace.process.communicate(timeout=10)
        assert trace.process.returncode == 1, stdout + stderr
        assert stdout == ""
        assert "load worker policy differs from request" in stderr
        text = trace.log.read_text()
        assert "= 3 (SCHED_BATCH) (DELAYED)" in text
        assert "INJECTED" not in text
        assert not (workspace / "worker.json").exists()
    assert os.sched_getscheduler(0) == policy
    assert os.sched_getaffinity(0) == affinity


@pytest.mark.parametrize(
    "field", ["worker_pid", "started_ns", "finished_ns", "duplicate_worker_pid", "duplicate_chunks"]
)
def test_actual_completed_receipt_corruption(native_run: Path, tmp_path: Path, field: str) -> None:
    """Alter an actual completed worker receipt before the launcher verifies it.

    Parameters
    ----------
    native_run
        Real production native controller and RTL plant executable.
    tmp_path
        Exclusive native artifacts, original receipt and negative mutation.
    field
        Actual identity, interval or member-uniqueness requirement to violate deliberately.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    workspace = tmp_path / "worker"
    journal = tmp_path / "load.json"
    with trace_command(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load.py"),
            "--profile",
            "idle",
            "--cpu",
            str(min(os.sched_getaffinity(0))),
            "--journal",
            str(journal),
            "--workspace",
            str(workspace),
            "--",
            str(native_run.resolve()),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "raw.csv"),
        ],
        "exit_group:delay_enter=2s:when=1",
        tmp_path / "receipt.strace",
    ) as trace:
        receipt_file = workspace / "worker.json"
        original, receipt = _wait_for_receipt(trace, receipt_file)
        worker = receipt["worker_pid"]
        assert worker in trace.descriptors
        assert not select.select([trace.descriptors[worker]], [], [], 0)[0]
        assert receipt["started_ns"] < receipt["finished_ns"]
        assert receipt["counters"]["chunks"] > 0
        (tmp_path / "original_worker.json").write_bytes(original)
        if field == "duplicate_worker_pid":
            altered = original.replace(b"{", b'{"worker_pid":0,', 1)
            expected = "duplicate JSON key: worker_pid"
        elif field == "duplicate_chunks":
            altered = original.replace(b'"chunks":', b'"chunks":0,"chunks":', 1)
            expected = "duplicate JSON key: chunks"
        else:
            receipt[field] = {
                "worker_pid": worker + 1,
                "started_ns": receipt["finished_ns"] + 1,
                "finished_ns": 0,
            }[field]
            altered = json.dumps(receipt, indent=2).encode() + b"\n"
            expected = "load collection does not cover native execution"
        receipt_file.write_bytes(altered)
        assert hashlib.sha256(original).digest() != hashlib.sha256(altered).digest()
        stdout, stderr = trace.process.communicate(timeout=12)
        assert trace.process.returncode == 1, stdout + stderr
        assert stdout.startswith("simulation_only ")
        assert expected in stderr
        assert not journal.exists()
        assert receipt_file.read_bytes() == altered
        assert (tmp_path / "events.bin").stat().st_size > 0
        assert "INJECTED" not in trace.log.read_text()


def _wait_for_receipt(trace: OwnedTrace, receipt_file: Path) -> tuple[bytes, dict[str, Any]]:
    """Read actual producer JSON while retaining the live traced process identities.

    Parameters
    ----------
    trace
        Exclusively owned tracer and descendant pidfds.
    receipt_file
        Actual worker completion file to observe for at most twelve seconds.

    Returns
    -------
    tuple of bytes and dict
        Original producer bytes and their decoded receipt.
    """
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        trace.observe()
        if receipt_file.exists():
            original = receipt_file.read_bytes()
            try:
                receipt = json.loads(original)
            except json.JSONDecodeError:
                pass
            else:
                return original, receipt
        assert trace.process.poll() is None
        time.sleep(0.005)
    pytest.fail("actual completed worker receipt was not observed")
