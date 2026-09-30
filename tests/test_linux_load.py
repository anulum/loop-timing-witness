# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host load against real native controller and RTL

"""Exercise all host load profiles through actual production process entry points."""

from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest
from linux_load_config import PROFILES
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT

__all__ = ["native_run"]


@pytest.mark.parametrize("profile", PROFILES)
def test_actual_profiles(native_run: Path, tmp_path: Path, profile: str) -> None:
    """Run each bounded real load during the production native RTL controller.

    Parameters
    ----------
    native_run
        Actual production controller and plant/AXI simulator.
    tmp_path
        Exclusive working allocation.
    profile
        Idle, arithmetic, memory/cache, loopback UDP or owned storage.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    priority = os.sched_getparam(0).sched_priority
    cpu = min(affinity)
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    journal = tmp_path / "load.json"
    workspace = tmp_path / "worker"
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load.py"),
            "--profile",
            profile,
            "--cpu",
            str(cpu),
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
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("simulation_only ")
    receipt = json.loads(journal.read_bytes())
    assert receipt["profile"] == profile
    assert receipt["native_returncode"] == 0
    assert (
        receipt["started_ns"]
        <= receipt["native_started_ns"]
        <= receipt["native_finished_ns"]
        <= receipt["finished_ns"]
    )
    assert receipt["worker_pid"] != receipt["native_pid"]
    assert receipt["policy"]["affinity_cpus"] == [cpu]
    assert receipt["policy"]["scheduler"] == os.SCHED_OTHER
    assert receipt["policy"]["priority"] == 0
    counters = receipt["counters"]
    chunks = counters["chunks"]
    assert chunks >= 1
    count_key = {
        "cpu": "arithmetic_operations",
        "memory": "memory_touches",
        "network": "datagrams",
        "storage": "fsyncs",
        "idle": "idle_waits",
    }[profile]
    assert counters[count_key] >= chunks
    if profile == "network":
        assert counters["bytes_sent"] == counters["bytes_received"] == chunks * 4096
        assert receipt["network_scope"] == "loopback_udp"
    if profile == "storage":
        assert counters["bytes_written"] == counters["bytes_read"] == chunks * 4096
        assert (workspace / "storage.bin").read_bytes() == bytes(range(256)) * 16
        assert receipt["storage_scope"] == "owned_file_fsync"
    with (tmp_path / "raw.csv").open(newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 32
    assert (tmp_path / "events.bin").stat().st_size > 0
    for pid in (receipt["worker_pid"], receipt["native_pid"]):
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler
    assert os.sched_getparam(0).sched_priority == priority


def test_native_failure_retained(native_run: Path, tmp_path: Path) -> None:
    """Preserve the real native argument refusal in a completed load receipt.

    Parameters
    ----------
    native_run
        Actual production native executable.
    tmp_path
        Exclusive output allocation.
    """
    journal = tmp_path / "load.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load.py"),
            "--profile",
            "cpu",
            "--cpu",
            str(min(os.sched_getaffinity(0))),
            "--journal",
            str(journal),
            "--workspace",
            str(tmp_path / "worker"),
            "--",
            str(native_run.resolve()),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(journal.read_bytes())["native_returncode"] == 1
    assert not (tmp_path / "events.bin").exists()


@pytest.mark.parametrize("failure", ["timeout", "worker_exit", "worker_stop"])
def test_actual_owned_failure(native_run: Path, tmp_path: Path, failure: str) -> None:
    """Terminate a real long native run on lifetime expiry or actual worker loss.

    Parameters
    ----------
    native_run
        Production native controller and actual plant/AXI model.
    tmp_path
        Exclusive partial-run and worker storage.
    failure
        Native timeout, owned worker SIGTERM or stopped worker requiring kill escalation.
    """
    config = tmp_path / "long.conf"
    config.write_text(
        configuration("pid", "none").replace("pid 32", "pid 100000"), encoding="utf-8"
    )
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "tools/linux_load.py"),
        "--profile",
        "cpu",
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--journal",
        str(tmp_path / "load.json"),
        "--workspace",
        str(tmp_path / "worker"),
        "--timeout",
        "1" if failure != "worker_exit" else "10",
        "--",
        str(native_run.resolve()),
        str(config),
        str(tmp_path / "events.bin"),
        str(tmp_path / "raw.csv"),
    ]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as process:
        # Coverage initializes each Python child before the launcher creates workers.
        # This bounds observation only; the actual native lifetime remains unchanged.
        deadline = time.monotonic() + 30
        children: list[int] = []
        while len(children) < 2 and process.poll() is None and time.monotonic() < deadline:
            children = [
                int(pid)
                for pid in Path(f"/proc/{process.pid}/task/{process.pid}/children")
                .read_text()
                .split()
            ]
            if len(children) < 2:
                time.sleep(0.01)
        assert len(children) == 2
        if failure != "timeout":
            workers = [
                pid
                for pid in children
                if b"linux_load_worker.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
            ]
            assert len(workers) == 1
            descriptor = os.pidfd_open(workers[0])
            try:
                signal.pidfd_send_signal(
                    descriptor, signal.SIGTERM if failure == "worker_exit" else signal.SIGSTOP
                )
            finally:
                os.close(descriptor)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 1, stdout + stderr
        assert ("worker exited" if failure == "worker_exit" else "timed out") in stderr
    assert not (tmp_path / "load.json").exists()
    assert (tmp_path / "worker/worker.log").exists()
    for pid in children:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


@pytest.mark.parametrize("failure", ["timeout", "identity"])
def test_actual_readiness_failure(native_run: Path, tmp_path: Path, failure: str) -> None:
    """Refuse a stopped real worker or an identity-corrupted frame on its actual pipe.

    Parameters
    ----------
    native_run
        Production native executable, which must not launch before worker readiness.
    tmp_path
        Exclusive real worker and journal directory.
    failure
        Missing readiness due to SIGSTOP or altered pipe identity from an external writer.
    """
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "tools/linux_load.py"),
        "--profile",
        "cpu",
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--journal",
        str(tmp_path / "load.json"),
        "--workspace",
        str(tmp_path / "worker"),
        "--",
        str(native_run.resolve()),
    ]
    descriptor = None
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as process:
        try:
            # Allow subprocess coverage startup before observing the real worker.
            deadline = time.monotonic() + 30
            workers: list[int] = []
            while not workers and process.poll() is None and time.monotonic() < deadline:
                children = (
                    Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()
                )
                workers = [
                    int(pid)
                    for pid in children
                    if b"linux_load_worker.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
                ]
                if not workers:
                    time.sleep(0.001)
            assert len(workers) == 1
            descriptor = os.pidfd_open(workers[0])
            signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
            if failure == "identity":
                with Path(f"/proc/{workers[0]}/fd/1").open("wb", buffering=0) as pipe:
                    pipe.write((json.dumps({"ready": True, "pid": workers[0] + 1}) + "\n").encode())
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 1, stdout + stderr
            assert ("timed out" if failure == "timeout" else "readiness differs") in stderr
            assert not (tmp_path / "load.json").exists()
        finally:
            if descriptor is not None:
                with suppress(ProcessLookupError):
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                os.close(descriptor)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
