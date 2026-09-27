# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual worker control pipe and Linux resource failures

"""Exercise the actual owned worker CLI with real pipe EOF and exclusive resources."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from linux_load_config import PROFILES

from conftest import REPOSITORY_ROOT


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("size", [4097, 60000])
def test_actual_eof_chunk(tmp_path: Path, profile: str, size: int) -> None:
    """Complete real work before honoring an already closed owner control pipe.

    Parameters
    ----------
    tmp_path
        Exclusive actual worker workspace.
    profile
        Requested production load profile.
    size
        Odd working-set size or the actual allowed UDP maximum.
    """
    affinity = os.sched_getaffinity(0)
    scheduler = os.sched_getscheduler(0)
    cpu = min(affinity)
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load_worker.py"),
            profile,
            str(cpu),
            str(size),
            str(tmp_path),
        ],
        input=b"",
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    ready = json.loads(result.stdout)
    receipt = json.loads((tmp_path / "worker.json").read_bytes())
    assert ready == {"ready": True, "pid": receipt["worker_pid"]}
    assert receipt["profile"] == profile
    assert receipt["working_set_bytes"] == size
    assert receipt["policy"]["affinity_cpus"] == [cpu]
    assert receipt["policy"]["scheduler"] == os.SCHED_OTHER
    assert receipt["policy"]["priority"] == 0
    assert receipt["finished_ns"] > receipt["started_ns"]
    counters = receipt["counters"]
    assert counters["chunks"] == 1
    expected_key = {
        "cpu": "arithmetic_operations",
        "memory": "memory_touches",
        "network": "datagrams",
        "storage": "fsyncs",
        "idle": "idle_waits",
    }[profile]
    expected = 4096 if profile == "cpu" else (size + 63) // 64 if profile == "memory" else 1
    assert counters[expected_key] == expected
    if profile == "network":
        assert counters["bytes_sent"] == counters["bytes_received"] == size
    if profile == "storage":
        assert counters["bytes_written"] == counters["bytes_read"] == size
        assert (tmp_path / "storage.bin").stat().st_size == size
        assert receipt["checksum"] == sum((tmp_path / "storage.bin").read_bytes())
    with pytest.raises(ProcessLookupError):
        os.kill(receipt["worker_pid"], 0)
    assert os.sched_getaffinity(0) == affinity
    assert os.sched_getscheduler(0) == scheduler


@pytest.mark.parametrize(
    "failure", ["buffer", "cpu", "workspace", "storage_collision", "receipt_collision"]
)
def test_real_worker_refusal(tmp_path: Path, failure: str) -> None:
    """Refuse actual invalid requests or exclusive-path conflicts without overwriting files.

    Parameters
    ----------
    tmp_path
        Exclusive fixture directory with owner-created conflict files.
    failure
        Public request bound or actual filesystem collision to exercise.
    """
    affinity = os.sched_getaffinity(0)
    cpu = max(affinity) + 1 if failure == "cpu" else min(affinity)
    size = 4095 if failure == "buffer" else 4096
    workspace = tmp_path / "absent" if failure == "workspace" else tmp_path
    profile = "storage" if failure == "storage_collision" else "cpu"
    name = "storage.bin" if failure == "storage_collision" else "worker.json"
    if failure in {"storage_collision", "receipt_collision"}:
        (tmp_path / name).write_bytes(b"preserve owner bytes")
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load_worker.py"),
            profile,
            str(cpu),
            str(size),
            str(workspace),
        ],
        input=b"",
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert b"Linux load worker: FAIL:" in result.stderr
    if failure in {"storage_collision", "receipt_collision"}:
        assert (tmp_path / name).read_bytes() == b"preserve owner bytes"
    else:
        assert not (workspace / "worker.json").exists()
    assert os.sched_getaffinity(0) == affinity


def test_actual_worker_api(tmp_path: Path) -> None:
    """Call the public worker main API in a real owned child with control-pipe EOF.

    Parameters
    ----------
    tmp_path
        Exclusive actual worker receipt destination.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from linux_load_worker import main; raise SystemExit(main())",
            "idle",
            str(min(os.sched_getaffinity(0))),
            "4096",
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT / "tools",
        input=b"",
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    ready = json.loads(result.stdout)
    receipt = json.loads((tmp_path / "worker.json").read_bytes())
    assert ready == {"ready": True, "pid": receipt["worker_pid"]}
    assert receipt["profile"] == "idle"
    assert receipt["counters"]["chunks"] == receipt["counters"]["idle_waits"] == 1
    with pytest.raises(ProcessLookupError):
        os.kill(receipt["worker_pid"], 0)


@pytest.mark.parametrize("profile", ["network", "storage"])
def test_actual_transfer_corruption(tmp_path: Path, profile: str) -> None:
    """Reject actual foreign UDP data or concurrent modification of the owned working file.

    Parameters
    ----------
    tmp_path
        Exclusive real worker resource directory.
    profile
        Actual transfer boundary to perturb after the worker reports readiness.
    """
    command = [
        sys.executable,
        str(REPOSITORY_ROOT / "tools/linux_load_worker.py"),
        profile,
        str(min(os.sched_getaffinity(0))),
        "4096",
        str(tmp_path),
    ]
    with subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as process:
        try:
            assert process.stdout is not None
            ready = json.loads(process.stdout.readline())
            assert ready == {"ready": True, "pid": process.pid}
            if profile == "network":
                inodes = {
                    target[8:-1]
                    for fd in Path(f"/proc/{process.pid}/fd").iterdir()
                    if (target := str(fd.readlink())).startswith("socket:[")
                }
                ports = {
                    int(fields[1].split(":")[1], 16)
                    for line in Path(f"/proc/{process.pid}/net/udp").read_text().splitlines()[1:]
                    if len(fields := line.split()) > 9 and fields[9] in inodes
                }
                assert len(inodes) == len(ports) == 2
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for port in ports:
                        sender.sendto(b"unexpected peer data", ("127.0.0.1", port))
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                if profile == "storage":
                    with (tmp_path / "storage.bin").open("r+b") as stream:
                        stream.write(b"\xff" * 4096)
                time.sleep(0.001)
            assert process.poll() == 1
            _, stderr = process.communicate(timeout=5)
            assert (b"datagram differs" if profile == "network" else b"readback differs") in stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert not (tmp_path / "worker.json").exists()
