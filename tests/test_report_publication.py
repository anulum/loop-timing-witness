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

from loop_timing_witness.report_publication import DirectoryPublication, publish_report_directory

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


def test_report_directory_lands_only_when_every_file_is_staged(tmp_path: Path) -> None:
    """Publish complete contents and remove the staging tree after a failed file.

    Parameters
    ----------
    tmp_path
        Exclusive parent for the report and its staging directories.
    """
    report = tmp_path / "report"
    publish_report_directory(report, {"a.json": b"{}\n", "b.csv": b"x\r\n"})
    assert {item.name: item.read_bytes() for item in report.iterdir()} == {
        "a.json": b"{}\n",
        "b.csv": b"x\r\n",
    }
    failed = tmp_path / "failed"
    with pytest.raises(FileNotFoundError):
        publish_report_directory(failed, {"a.json": b"{}", "missing/b.csv": b""})
    assert sorted(item.name for item in tmp_path.iterdir()) == ["report"]


def test_report_directory_refuses_existing_paths(tmp_path: Path) -> None:
    """Refuse a dangling symlink destination and an absent parent without debris.

    Parameters
    ----------
    tmp_path
        Exclusive parent holding the dangling link.
    """
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "absent-target")
    with pytest.raises(FileExistsError, match="report directory already exists"):
        publish_report_directory(link, {"a.json": b"{}"})
    with pytest.raises(FileNotFoundError, match="report parent does not exist"):
        publish_report_directory(tmp_path / "absent" / "report", {"a.json": b"{}"})
    assert [item.name for item in tmp_path.iterdir()] == ["linked"]
    assert not (tmp_path / "absent-target").exists()
