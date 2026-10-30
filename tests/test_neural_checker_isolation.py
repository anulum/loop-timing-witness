# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual source-checker kernel isolation

"""Exercise the real checker resource and network syscall boundary in an owned child."""

from __future__ import annotations

import errno
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_actual_checker_profile_denies_socket_and_sets_finite_limits() -> None:
    """Apply the production profile and observe actual kernel refusal without sending data."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import errno, json, resource, socket
from loop_timing_witness.neural_checker_isolation import isolate_checker
isolate_checker()
try:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError as error:
    socket_errno = error.errno
else:
    connection.close()
    socket_errno = None
print(json.dumps({
    "socket_errno": socket_errno,
    "expected_errno": errno.EPERM,
    "address_space": resource.getrlimit(resource.RLIMIT_AS),
    "cpu": resource.getrlimit(resource.RLIMIT_CPU),
    "file": resource.getrlimit(resource.RLIMIT_FSIZE),
    "core": resource.getrlimit(resource.RLIMIT_CORE),
}))
""",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["socket_errno"] == report["expected_errno"]
    assert report["address_space"] == [805306368, 805306368]
    assert report["cpu"] == [30, 30]
    assert report["file"] == [1048576, 1048576]
    assert report["core"] == [0, 0]


def test_actual_filter_denies_every_declared_network_and_x32_syscall() -> None:
    """Exercise the kernel filter with null arguments and a non-network stdin."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import ctypes, json, os
from loop_timing_witness.neural_checker_isolation import isolate_checker
library = ctypes.CDLL(None, use_errno=True)
invoke = library.syscall
invoke.argtypes = [ctypes.c_long] * 7
invoke.restype = ctypes.c_long
isolate_checker()
numbers = [*range(41, 56), 288, 299, 307, 425, 426, 427, 0x40000000, 0x40000029]
observed = {}
for number in numbers:
    ctypes.set_errno(0)
    status = invoke(number, 0, 0, 0, 0, 0, 0)
    observed[str(number)] = [status, ctypes.get_errno()]
print(json.dumps({
    'blocked': observed,
    'permitted_getpid': invoke(39, 0, 0, 0, 0, 0, 0),
    'actual_pid': os.getpid(),
}))
""",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    expected = {*range(41, 56), 288, 299, 307, 425, 426, 427, 0x40000000, 0x40000029}
    assert set(report["blocked"]) == {str(number) for number in expected}
    assert all(value == [-1, errno.EPERM] for value in report["blocked"].values())
    assert report["permitted_getpid"] == report["actual_pid"]


@pytest.mark.parametrize(
    ("call_number", "operation"), [(1, "PR_SET_NO_NEW_PRIVS"), (2, "PR_SET_SECCOMP")]
)
def test_actual_prctl_refusal_is_not_treated_as_isolation(
    tmp_path: Path, call_number: int, operation: str
) -> None:
    """Refuse either traced kernel setup call when ptrace injects actual EPERM.

    Parameters
    ----------
    tmp_path
        Owned actual syscall trace.
    call_number
        First no-new-privileges call or second filter-installation call.
    operation
        Required symbolic syscall argument in the injected trace record.
    """
    tracer = shutil.which("strace")
    assert tracer is not None
    trace = Path(tmp_path, "prctl.trace")
    result = subprocess.run(
        [
            tracer,
            "-qq",
            "-e",
            "trace=prctl",
            "-e",
            f"inject=prctl:error=EPERM:when={call_number}",
            "-o",
            str(trace),
            sys.executable,
            "-B",
            "-c",
            """
import ctypes, json
from loop_timing_witness.neural_checker_isolation import isolate_checker
try:
    isolate_checker()
except OSError as error:
    print(json.dumps({'error': str(error), 'errno': ctypes.get_errno()}))
else:
    raise SystemExit(3)
""",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "error": "Source checker kernel isolation is unavailable.",
        "errno": errno.EPERM,
    }
    lines = trace.read_text().splitlines()
    assert len(lines) == call_number
    assert lines[-1].startswith(f"prctl({operation},")
    assert "= -1 EPERM" in lines[-1]
    assert "(INJECTED)" in lines[-1]


def test_actual_linux32_uname_personality_refuses_the_selected_platform() -> None:
    """Observe the kernel's changed uname in a fresh interpreter before isolation."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import ctypes, os, sys
library = ctypes.CDLL(None, use_errno=True)
library.personality.argtypes = [ctypes.c_ulong]
library.personality.restype = ctypes.c_int
assert library.personality(8) >= 0, ctypes.get_errno()
os.execv(sys.executable, [sys.executable, '-B', '-c', sys.argv[1]])
""",
            """
import json, os, platform
from loop_timing_witness.neural_checker_isolation import isolate_checker
try:
    isolate_checker()
except OSError as error:
    print(json.dumps({
        'error': str(error),
        'machine': platform.machine(),
        'kernel_machine': os.uname().machine,
    }))
else:
    raise SystemExit(3)
""",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "error": "Source checker requires its selected Linux x86-64 platform.",
        "machine": "i686",
        "kernel_machine": "i686",
    }


def test_actual_inherited_hard_limit_cannot_be_silently_raised() -> None:
    """Refuse the selected profile when an actual inherited hard cap is lower."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import json, resource
from loop_timing_witness.neural_checker_isolation import isolate_checker
resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
try:
    isolate_checker()
except ValueError:
    print(json.dumps({'address_space': resource.getrlimit(resource.RLIMIT_AS)}))
else:
    raise SystemExit(3)
""",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"address_space": [536870912, 536870912]}


def test_actual_filter_is_inherited_by_new_threads_and_spawned_children() -> None:
    """Observe actual socket refusal in both subsequently created execution contexts."""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import json, socket, subprocess, sys, threading
from loop_timing_witness.neural_checker_isolation import isolate_checker

def blocked_socket() -> int:
    '''Return the actual kernel error without connecting or transmitting.'''
    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as error:
        return error.errno or 0
    connection.close()
    return 0

with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
    before_socket_allowed = True
isolate_checker()
thread_errors: list[int] = []
thread = threading.Thread(target=lambda: thread_errors.append(blocked_socket()))
thread.start()
thread.join()
child = subprocess.run(
    [sys.executable, '-B', '-c', '''
import json, socket
try:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError as error:
    print(json.dumps({'errno': error.errno}))
else:
    connection.close()
    raise SystemExit(3)
'''],
    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10, check=False,
)
print(json.dumps({
    'before_socket_allowed': before_socket_allowed,
    'thread_errors': thread_errors,
    'child_errno': json.loads(child.stdout)['errno'],
    'child_exit': child.returncode,
    'child_stderr': child.stderr,
}))
""",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "before_socket_allowed": True,
        "thread_errors": [errno.EPERM],
        "child_errno": errno.EPERM,
        "child_exit": 0,
        "child_stderr": "",
    }
