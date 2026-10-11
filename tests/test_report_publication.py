# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native report publication tests

"""Exercise the real Linux ABI, filesystem capability and atomic refusal."""

from __future__ import annotations

import ctypes
import errno
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.report_publication import DirectoryPublication

if TYPE_CHECKING:
    from pathlib import Path


def test_missing_native_capability_is_refused(tmp_path: Path) -> None:
    """A real vDSO library lacks the publication ABI and cannot start staging.

    Parameters
    ----------
    tmp_path
        Exclusive parent whose contents must remain empty.
    """
    library = ctypes.CDLL("linux-vdso.so.1", use_errno=True)
    with pytest.raises(OSError, match="requires Linux renameat2") as failure:
        DirectoryPublication(library).check(tmp_path)
    assert failure.value.errno == errno.ENOTSUP
    assert not list(tmp_path.iterdir())


def test_capability_probe_and_publication(tmp_path: Path) -> None:
    """A real probe cleans up before a complete directory moves into visibility.

    Parameters
    ----------
    tmp_path
        Exclusive parent for the probe, staged content and destination.
    """
    publication = DirectoryPublication(ctypes.CDLL(None, use_errno=True))
    publication.check(tmp_path)
    assert not list(tmp_path.iterdir())
    source = tmp_path / "source"
    source.mkdir()
    (source / "data").write_bytes(b"complete")
    inode = source.stat().st_ino
    target = tmp_path / "target"
    publication.publish(source, target)
    assert not source.exists()
    assert target.stat().st_ino == inode
    assert (target / "data").read_bytes() == b"complete"


def test_missing_source_preserves_destination(tmp_path: Path) -> None:
    """The actual kernel error is retained and creates no output directory.

    Parameters
    ----------
    tmp_path
        Exclusive parent with no staged source or report.
    """
    publication = DirectoryPublication(ctypes.CDLL(None, use_errno=True))
    with pytest.raises(FileNotFoundError) as failure:
        publication.publish(tmp_path / "missing", tmp_path / "target")
    assert failure.value.errno == errno.ENOENT
    assert not list(tmp_path.iterdir())


def test_readonly_parent_refuses_before_staging(tmp_path: Path) -> None:
    """Actual filesystem permissions refuse the capability probe without debris.

    Parameters
    ----------
    tmp_path
        Exclusive parent restored to its original mode after the refusal.
    """
    publication = DirectoryPublication(ctypes.CDLL(None, use_errno=True))
    mode = tmp_path.stat().st_mode
    tmp_path.chmod(0o500)
    try:
        with pytest.raises(PermissionError):
            publication.check(tmp_path)
        assert not list(tmp_path.iterdir())
    finally:
        tmp_path.chmod(mode)
