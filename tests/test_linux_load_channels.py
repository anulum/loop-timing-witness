# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real worker pipe endpoint ownership

"""Exercise actual pipe transfers, prompt EOF and context-owned descriptor closure."""

from __future__ import annotations

import os
import select
import subprocess
import sys

import pytest
from linux_load_channels import worker_channels

from conftest import REPOSITORY_ROOT


def test_actual_pipe_transfer_and_stop() -> None:
    """Transfer real bytes in both directions and deliver EOF before context exit."""
    with worker_channels() as channels:
        descriptors = [
            stream.fileno()
            for stream in (
                channels.child_input,
                channels.child_output,
                channels.readiness,
                channels.control,
            )
        ]
        assert len(set(descriptors)) == 4
        assert all(not os.get_inheritable(descriptor) for descriptor in descriptors)
        channels.control.write(b"owner command")
        channels.control.flush()
        assert channels.child_input.read(len(b"owner command")) == b"owner command"
        channels.child_output.write(b"worker readiness\n")
        channels.child_output.flush()
        assert select.select([channels.readiness], [], [], 1)[0]
        assert channels.readiness.readline() == b"worker readiness\n"
        channels.stop()
        channels.stop()
        assert channels.child_input.read() == b""
    for descriptor in descriptors:
        with pytest.raises(OSError, match="Bad file descriptor"):
            os.fstat(descriptor)


def test_actual_early_child_end_release() -> None:
    """Close parent copies so readiness sees EOF when no worker inherits a writer."""
    with worker_channels() as channels:
        descriptors = [channels.child_input.fileno(), channels.child_output.fileno()]
        channels.release_child_ends()
        channels.release_child_ends()
        assert select.select([channels.readiness], [], [], 1)[0]
        assert channels.readiness.read() == b""
        for descriptor in descriptors:
            with pytest.raises(OSError, match="Bad file descriptor"):
                os.fstat(descriptor)


def test_context_closes_on_pipe_failure() -> None:
    """Close owned descriptors after a real write to a pipe with no remaining reader."""
    descriptors: list[int] = []

    def write_to_closed_receiver() -> None:
        """Cause the actual kernel broken-pipe error through public channels."""
        with worker_channels() as channels:
            descriptors.extend(
                stream.fileno()
                for stream in (
                    channels.child_input,
                    channels.child_output,
                    channels.readiness,
                    channels.control,
                )
            )
            channels.release_child_ends()
            channels.control.write(b"owner command")
            channels.control.flush()

    with pytest.raises(BrokenPipeError):
        write_to_closed_receiver()
    for descriptor in descriptors:
        with pytest.raises(OSError, match="Bad file descriptor"):
            os.fstat(descriptor)


def test_released_descriptor_reuse() -> None:
    """Preserve a newly opened descriptor reusing an already released child-end number."""
    replacement = -1
    try:
        with worker_channels() as channels:
            released = {channels.child_input.fileno(), channels.child_output.fileno()}
            channels.release_child_ends()
            replacement = os.open("/dev/null", os.O_RDONLY)
            assert replacement in released
        assert os.fstat(replacement)
    finally:
        if replacement >= 0:
            os.close(replacement)


def test_second_pipe_allocation_failure() -> None:
    """Use a real child descriptor limit to fail the second pipe and close the first."""
    script = """
import errno
import os
import resource
from linux_load_channels import worker_channels

baseline = set()
for name in os.listdir('/proc/self/fd'):
    descriptor = int(name)
    try:
        os.fstat(descriptor)
    except OSError:
        continue
    baseline.add(descriptor)
assert baseline == {0, 1, 2}, baseline
limits = resource.getrlimit(resource.RLIMIT_NOFILE)
try:
    resource.setrlimit(resource.RLIMIT_NOFILE, (5, limits[1]))
    try:
        with worker_channels():
            raise AssertionError('second pipe unexpectedly allocated')
    except OSError as error:
        assert error.errno == errno.EMFILE, error
    for descriptor in (3, 4):
        try:
            os.fstat(descriptor)
        except OSError as error:
            assert error.errno == errno.EBADF, error
        else:
            raise AssertionError('first pipe descriptor leaked')
finally:
    resource.setrlimit(resource.RLIMIT_NOFILE, limits)
print('actual second-pipe allocation failure cleaned up')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT / "tools",
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "actual second-pipe allocation failure cleaned up"
