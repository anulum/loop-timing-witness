# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host faults while staging the checker, in both languages

"""Stage the source checker under a real host fault and require one refusal in both languages.

The owned checker directory becomes unwritable through the process umask, or
its writes exceed the process file-size limit. Python runs in this process
under the condition and Rust in a child started under the same condition; any
such operating-system failure is the same refusal.
"""

from __future__ import annotations

import os
import resource
import signal
from contextlib import contextmanager
from typing import TYPE_CHECKING

from neural_acquisition_support import build_neural_acquisition, make_writable
from neural_rust_support import assert_same_outcome, python_outcome, rust_outcome

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

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
