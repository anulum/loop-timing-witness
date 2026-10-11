# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual running, reaped and failed-scope process cleanup

"""Verify bounded cleanup without signalling an unrelated owned process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from contextlib import ExitStack

import pytest
from process_lifetime_support import finish_process, retain_process


@pytest.mark.parametrize("state", ["running", "reaped"])
def test_actual_process_cleanup_preserves_unrelated_process(state: str) -> None:
    """Close running or already reaped kernel identities without touching another child.

    Parameters
    ----------
    state
        Whether the target remains live or is reaped before its pidfd is cleaned up.
    """
    with (
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as unrelated,
        ExitStack() as resources,
    ):
        unrelated_descriptor = retain_process(unrelated)
        resources.callback(finish_process, unrelated, unrelated_descriptor)
        command = "import time; time.sleep(30)" if state == "running" else "pass"
        with subprocess.Popen([sys.executable, "-c", command]) as process:
            descriptor = retain_process(process)
            if state == "reaped":
                assert process.wait(timeout=5) == 0
            finish_process(process, descriptor)
            assert process.returncode == (-signal.SIGKILL if state == "running" else 0)
            with pytest.raises(OSError, match="Bad file descriptor"):
                os.fstat(descriptor)
        assert unrelated.poll() is None


def test_actual_failure_scope_still_ends_process() -> None:
    """Close the actual child and descriptor after a failure in its owning scope."""
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as process:
        descriptor = retain_process(process)
        resources = ExitStack()
        resources.callback(finish_process, process, descriptor)
        message = "deliberate owner failure"
        with pytest.raises(RuntimeError, match="deliberate owner failure"), resources:
            raise RuntimeError(message)
    assert process.returncode == -signal.SIGKILL
    with pytest.raises(OSError, match="Bad file descriptor"):
        os.fstat(descriptor)


def test_actual_descriptor_exhaustion_ends_child() -> None:
    """Refuse a real exhausted descriptor table after safely ending the new child."""
    script = """
import errno
import os
import resource
import signal
import subprocess
import sys
from process_lifetime_support import retain_process

with subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']) as process:
    limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    descriptors = []
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, limits[1]))
        while True:
            try:
                descriptors.append(os.open('/dev/null', os.O_RDONLY))
            except OSError as error:
                assert error.errno == errno.EMFILE
                break
        try:
            retain_process(process)
        except OSError as error:
            assert error.errno == errno.EMFILE
        else:
            raise AssertionError('pidfd unexpectedly allocated')
        assert process.returncode == -signal.SIGKILL
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        resource.setrlimit(resource.RLIMIT_NOFILE, limits)
print('actual EMFILE child cleanup verified')
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "actual EMFILE child cleanup verified\n"
