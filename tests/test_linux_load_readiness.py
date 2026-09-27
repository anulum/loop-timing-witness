# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual bounded readiness framing and exact field types

"""Check real producer bytes on actual pipes, with explicit negative frame mutations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from linux_load_channels import worker_channels
from linux_load_readiness import MAX_READINESS_BYTES, read_ready_pid

from conftest import REPOSITORY_ROOT


@pytest.fixture(scope="module")
def actual_ready_frame(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, int]:
    """Obtain readiness from real first-chunk work with an already closed owner stdin.

    Parameters
    ----------
    tmp_path_factory
        Exclusive actual worker workspace allocation.

    Returns
    -------
    tuple of bytes and int
        Actual complete stdout line and its producer's process ID.
    """
    workspace = tmp_path_factory.mktemp("readiness_producer")
    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tools/linux_load_worker.py"),
            "idle",
            str(min(os.sched_getaffinity(0))),
            "4096",
            str(workspace),
        ],
        input=b"",
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads((workspace / "worker.json").read_bytes())
    assert receipt["counters"]["chunks"] == 1
    assert json.loads(result.stdout) == {"ready": True, "pid": receipt["worker_pid"]}
    return result.stdout, receipt["worker_pid"]


@pytest.mark.parametrize("padding", [False, True])
def test_actual_frame(actual_ready_frame: tuple[bytes, int], *, padding: bool) -> None:
    """Accept real producer bytes, including valid whitespace at the exact size bound.

    Parameters
    ----------
    actual_ready_frame
        Readiness bytes from an actual completed worker.
    padding
        Whether to prefix whitespace to the 4096-byte inclusive frame limit.
    """
    frame, pid = actual_ready_frame
    if padding:
        frame = b" " * (MAX_READINESS_BYTES - len(frame)) + frame
    with worker_channels() as channels:
        channels.child_output.write(frame)
        channels.child_output.flush()
        assert read_ready_pid(channels.readiness) == pid


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), -float("inf"), float("nan")])
def test_invalid_deadline(actual_ready_frame: tuple[bytes, int], timeout: float) -> None:
    """Refuse invalid budgets before consuming already available actual producer bytes.

    Parameters
    ----------
    actual_ready_frame
        Actual producer bytes retained on the real pipe.
    timeout
        Nonpositive or nonfinite budget to reject.
    """
    frame, pid = actual_ready_frame
    with worker_channels() as channels:
        channels.child_output.write(frame)
        channels.child_output.flush()
        with pytest.raises(ValueError, match="finite and positive"):
            read_ready_pid(channels.readiness, timeout)
        assert read_ready_pid(channels.readiness) == pid


@pytest.mark.parametrize(
    "violation",
    [
        "numeric_ready",
        "false",
        "missing",
        "extra",
        "bool_pid",
        "float_pid",
        "zero",
        "negative",
        "list",
    ],
)
def test_negative_field_mutation(actual_ready_frame: tuple[bytes, int], violation: str) -> None:
    """Refuse a deliberately altered actual readiness object rather than coercing fields.

    Parameters
    ----------
    actual_ready_frame
        Original actual producer frame, never replaced by synthetic valid data.
    violation
        Exact key, Boolean or PID type/value requirement to violate.
    """
    original = json.loads(actual_ready_frame[0])
    record: object = original
    if violation in {"numeric_ready", "false"}:
        original["ready"] = 1 if violation == "numeric_ready" else False
    elif violation == "missing":
        del original["ready"]
    elif violation == "extra":
        original["extra"] = "negative input"
    elif violation == "list":
        record = [original]
    else:
        original["pid"] = {
            "bool_pid": True,
            "float_pid": float(original["pid"]),
            "zero": 0,
            "negative": -original["pid"],
        }[violation]
    with worker_channels() as channels:
        channels.child_output.write(json.dumps(record).encode() + b"\n")
        channels.child_output.flush()
        with pytest.raises(ValueError, match="readiness"):
            read_ready_pid(channels.readiness)


@pytest.mark.parametrize("violation", ["oversized", "unterminated", "json", "expired", "empty"])
def test_actual_framing_failure(actual_ready_frame: tuple[bytes, int], violation: str) -> None:
    """Exercise actual byte limits, EOF, malformed JSON and real deadline expiry.

    Parameters
    ----------
    actual_ready_frame
        Original actual worker frame for an unterminated-line or expired-budget case.
    violation
        Pipe framing or timeout condition to produce through actual kernel I/O.
    """
    frame = {
        "oversized": b" " * MAX_READINESS_BYTES + b"\n",
        "unterminated": actual_ready_frame[0][:-1],
        "json": b"{\n",
        "expired": actual_ready_frame[0],
        "empty": b"",
    }[violation]
    with worker_channels() as channels:
        channels.child_output.write(frame)
        channels.child_output.flush()
        if violation == "unterminated":
            channels.release_child_ends()
        timeout = 1e-30 if violation == "expired" else 0.01 if violation == "empty" else 1
        with pytest.raises((TimeoutError, ValueError)):
            read_ready_pid(channels.readiness, timeout)


@pytest.mark.parametrize("slow", [False, True])
def test_actual_chunked_frame(actual_ready_frame: tuple[bytes, int], *, slow: bool) -> None:
    """Read real delayed pipe chunks under one deadline without restarting its budget.

    Parameters
    ----------
    actual_ready_frame
        Actual producer's complete line and PID.
    slow
        Whether to stream one byte per interval beyond the total permitted budget.
    """
    frame, pid = actual_ready_frame
    stopping = Event()
    with worker_channels() as channels, ThreadPoolExecutor(max_workers=1) as executor:
        channels.child_output.write(frame[:1])
        channels.child_output.flush()

        def send_remaining() -> None:
            """Deliver remaining actual producer bytes through the real writer endpoint."""
            chunks = [bytes([byte]) for byte in frame[1:]] if slow else [frame[1:]]
            for chunk in chunks:
                if stopping.wait(0.02):
                    return
                channels.child_output.write(chunk)
                channels.child_output.flush()

        pending = executor.submit(send_remaining)
        try:
            if slow:
                with pytest.raises(TimeoutError, match="complete worker readiness"):
                    read_ready_pid(channels.readiness, 0.05)
            else:
                assert read_ready_pid(channels.readiness, 1) == pid
        finally:
            stopping.set()
            pending.result(timeout=1)


@pytest.mark.parametrize("violation", ["duplicate_ready", "duplicate_pid", "utf16", "invalid_utf8"])
def test_strict_json_frame(actual_ready_frame: tuple[bytes, int], violation: str) -> None:
    """Reject shadowed members and non-UTF-8 encodings of actual worker frames.

    Parameters
    ----------
    actual_ready_frame
        Original production worker bytes, replayed only after deliberate invalidation.
    violation
        Repeated member or encoding requirement to violate on the actual pipe.
    """
    frame, _ = actual_ready_frame
    if violation == "duplicate_ready":
        frame = frame.replace(b"{", b'{"ready":false,', 1)
        expected = "duplicate JSON key: ready"
    elif violation == "duplicate_pid":
        frame = frame.replace(b"{", b'{"pid":0,', 1)
        expected = "duplicate JSON key: pid"
    elif violation == "utf16":
        frame = frame.decode().encode("utf-16")
        expected = "not UTF-8"
    else:
        frame = b"\xff" + frame
        expected = "not UTF-8"
    with worker_channels() as channels:
        channels.child_output.write(frame)
        channels.child_output.flush()
        with pytest.raises(ValueError, match=expected):
            read_ready_pid(channels.readiness)
