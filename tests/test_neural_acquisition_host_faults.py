# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host faults while staging the checker, in both languages

"""Run the source checker under real host faults and require one outcome in both languages.

The owned checker directory becomes unwritable through the process umask, or
its writes exceed the process file-size limit. Python runs in this process
under the condition and Rust in a child started under the same condition; any
such operating-system failure is the same refusal. Checker programs that skip,
add or remove traced files run under the traced host installation.
"""

from __future__ import annotations

import os
import resource
import signal
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from neural_acquisition_support import (
    CHECKER,
    build_neural_acquisition,
    calibrated_host_installation,
    make_writable,
    rebind_image,
)
from neural_rust_support import assert_same_outcome, python_outcome, rust_outcome

if TYPE_CHECKING:
    from collections.abc import Iterator

    from loop_timing_witness.neural_checker_installation import NeuralCheckerInstallation

_REFUSAL = {"refusal": "Cannot bind the complete public neural acquisition."}
_UMASK = ("sh", "-c", 'umask 277; exec "$@"', "sh")
# An ignored SIGXFSZ survives exec, so a write past the limit fails with EFBIG.
# The limit would also truncate an instrumented consumer's coverage profile, so
# that one profile is discarded instead of written.
_FILE_SIZE = (
    "sh",
    "-c",
    "trap '' XFSZ; LLVM_PROFILE_FILE=/dev/null exec prlimit --fsize=4096: \"$@\"",
    "sh",
)


@contextmanager
def _umask(mask: int) -> Iterator[None]:
    """Apply one process umask for the duration of the block.

    Parameters
    ----------
    mask
        Permission bits removed from new files and directories.

    Yields
    ------
    None
        Control while the umask applies.
    """
    previous = os.umask(mask)
    try:
        yield
    finally:
        os.umask(previous)


@contextmanager
def _file_size_limit(limit: int) -> Iterator[None]:
    """Lower the soft file-size limit, with the limit signal ignored, for the block.

    Parameters
    ----------
    limit
        Largest file size in bytes a write may reach.

    Yields
    ------
    None
        Control while the limit applies.
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    handler = signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, hard))
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
        signal.signal(signal.SIGXFSZ, handler)


def test_unwritable_checker_staging_is_one_refusal(tmp_path: Path) -> None:
    """Refuse alike when the owned checker directory cannot hold the source copy.

    Parameters
    ----------
    tmp_path
        Owned acquisition and Rust outcome directories.
    """
    acquisition = build_neural_acquisition(tmp_path / "run")
    directory = tmp_path / "rust"
    try:
        with _umask(0o277):
            python = python_outcome(acquisition)
        rust = rust_outcome(acquisition, directory, wrapper=_UMASK)
    finally:
        make_writable(tmp_path)
    assert python == _REFUSAL
    assert_same_outcome(python, rust)


def test_oversized_checker_staging_is_one_refusal(tmp_path: Path) -> None:
    """Refuse alike when a source copy exceeds the process file-size limit.

    Parameters
    ----------
    tmp_path
        Owned acquisition and Rust outcome directories.
    """
    acquisition = build_neural_acquisition(tmp_path / "run")
    directory = tmp_path / "rust"
    try:
        with _file_size_limit(4096):
            python = python_outcome(acquisition)
        rust = rust_outcome(acquisition, directory, wrapper=_FILE_SIZE)
    finally:
        make_writable(tmp_path)
    assert python == _REFUSAL
    assert_same_outcome(python, rust)


@pytest.fixture(scope="module")
def host_installation(tmp_path_factory: pytest.TempPathFactory) -> NeuralCheckerInstallation:
    """Calibrate one host installation from the real traced checker runs.

    Parameters
    ----------
    tmp_path_factory
        Owned calibration directory.

    Returns
    -------
    NeuralCheckerInstallation
        Running interpreter, actual tracer and every observed runtime file.
    """
    return calibrated_host_installation(tmp_path_factory.mktemp("calibration"))


_SKIPS_CLOSURE = (
    b"import sys\nif sys.argv[1] == '--check':\n    print('check passed')\n"
    b"    raise SystemExit(0)\n" + CHECKER.encode()
)
_OPENS_OUTSIDE = b"open('/proc/version').read()\n" + CHECKER.encode()
_LIVE_MODULE = (
    b"import sys, types\nlive = types.ModuleType('sc_neurocore_live')\n"
    b"live.__file__ = '/proc/version'\nsys.modules['sc_neurocore_live'] = live\n" + CHECKER.encode()
)
_REMOVES_OPENED = (
    b"import os\nopen('gone.txt', 'w').write('x')\nopen('gone.txt').read()\n"
    b"os.remove('gone.txt')\n" + CHECKER.encode()
)
_NO_OBSERVATION = CHECKER.encode() + b"import os\nos._exit(0)\n"
_REMOVES_TRACE = b"import os\nos.remove('checker-open.log')\n" + CHECKER.encode()

_TRACED: dict[str, tuple[bytes, str, str]] = {
    "skips-closure": (
        _SKIPS_CLOSURE,
        "source_binding",
        "did not open its complete admitted source closure",
    ),
    "opens-outside": (
        _OPENS_OUTSIDE,
        "source_binding",
        "opened a file outside its complete runtime binding",
    ),
    "live-module": (
        _LIVE_MODULE,
        "source_binding",
        "imported a live or unbound SC source fallback",
    ),
    "removes-opened": (
        _REMOVES_OPENED,
        "refusal",
        "Actual checker observed file is unavailable.",
    ),
    "removes-trace": (
        _REMOVES_TRACE,
        "source_binding",
        "opened-file observation is unavailable",
    ),
    "no-observation": (
        _NO_OBSERVATION,
        "source_binding",
        "opened-file observation is unavailable",
    ),
}


@pytest.mark.parametrize("fault", list(_TRACED))
def test_traced_host_fault_has_one_outcome(
    host_installation: NeuralCheckerInstallation, tmp_path: Path, fault: str
) -> None:
    """Require the same refusal or source finding for one traced host checker fault.

    Parameters
    ----------
    host_installation
        Calibrated reviewed host installation.
    tmp_path
        Owned acquisition and Rust outcome directories.
    fault
        Named checker program fault.
    """
    program, kind, message = _TRACED[fault]
    acquisition = build_neural_acquisition(
        tmp_path / "run", installation=host_installation, program=program
    )
    try:
        python = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    if kind == "refusal":
        assert python.get("refusal") == message, python
    else:
        findings = python["report"][kind]["findings"]
        assert any(message in finding for finding in findings), findings


def test_deadline_stops_the_whole_checker_group(tmp_path: Path) -> None:
    """Stop a checker at its image deadline and report the interrupted run alike.

    Parameters
    ----------
    tmp_path
        Owned acquisition and Rust outcome directories.
    """
    program = b"import time\ntime.sleep(5)\n" + CHECKER.encode()
    acquisition = rebind_image(
        build_neural_acquisition(tmp_path / "run", program=program),
        lambda binding: binding.update(deadline_seconds=1),
    )
    try:
        python = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    findings = python["report"]["completion"]["findings"]
    assert "Actual source checker lacks a complete reaped observation." in findings


@pytest.mark.parametrize("host", [False, True])
def test_failed_wait_stops_the_checker_group(
    host_installation: NeuralCheckerInstallation, tmp_path: Path, *, host: bool
) -> None:
    """Refuse when waiting for the checker fails, after stopping its whole group.

    The first wait of each traced Rust process fails with an injected error,
    including the verifier's own first wait. The Python verifier stops the
    group and lets the same operating-system error become this refusal, which
    the unchanged run here does not reach.

    Parameters
    ----------
    host_installation
        Calibrated reviewed host installation.
    tmp_path
        Owned acquisition and Rust outcome directories.
    host
        Run the traced host installation instead of the image.
    """
    installation = host_installation if host else None
    acquisition = build_neural_acquisition(tmp_path / "run", installation=installation)
    # The test harness runs the consumer in a thread, so threads are followed.
    injected = ("strace", "-f", "-o", "/dev/null", "-e", "inject=wait4:error=ECHILD:when=1")
    try:
        rust = rust_outcome(acquisition, tmp_path / "rust", wrapper=injected)
    finally:
        make_writable(tmp_path)
    assert rust == _REFUSAL


@pytest.mark.parametrize("host", [False, True])
def test_non_utf8_working_directory_is_refused(
    host_installation: NeuralCheckerInstallation,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    host: bool,
) -> None:
    """Refuse a checker working directory a report could not record exactly.

    Parameters
    ----------
    host_installation
        Calibrated reviewed host installation.
    tmp_path
        Owned acquisition, temporary parent and Rust outcome directories.
    monkeypatch
        Selects the temporary parent for the Python verifier.
    host
        Run the traced host installation instead of the image.
    """
    selected = os.fsdecode(os.fsencode(tmp_path) + b"/parent-\xff")
    Path(selected).mkdir()
    installation = host_installation if host else None
    acquisition = build_neural_acquisition(tmp_path / "run", installation=installation)
    monkeypatch.setattr(tempfile, "tempdir", selected)
    try:
        python = python_outcome(acquisition)
        rust = rust_outcome(acquisition, tmp_path / "rust", wrapper=("env", f"TMPDIR={selected}"))
    finally:
        make_writable(tmp_path)
    assert python == {"refusal": "Checker path requires exact UTF-8."}
    assert_same_outcome(python, rust)


def test_malformed_worker_observation_is_refused(tmp_path: Path) -> None:
    """Refuse alike an observation file the checker left in place of the worker's.

    Parameters
    ----------
    tmp_path
        Owned acquisition and Rust outcome directories.
    """
    program = CHECKER.encode() + (
        b"open('checker-observation.json', 'w').write('[]')\nimport os\nos._exit(0)\n"
    )
    acquisition = build_neural_acquisition(tmp_path / "run", program=program)
    try:
        python = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    assert python == {"refusal": "Invalid original actual checker observation."}
