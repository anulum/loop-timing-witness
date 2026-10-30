# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Linux report directory publication

"""Bind atomic Linux directory publication without replacing an existing path."""

from __future__ import annotations

import ctypes
import errno
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

AT_FDCWD = -100
RENAME_NOREPLACE = 1


class DirectoryPublication:
    """Use a native Linux library's no-replacement directory rename.

    Parameters
    ----------
    library
        Loaded native library using ``use_errno=True``. The report writer binds
        the current process library lazily, leaving pure analysis independent.

    Raises
    ------
    OSError
        If the library cannot provide Linux atomic no-replacement publication.
    """

    def __init__(self, library: ctypes.CDLL) -> None:
        """Resolve and configure the native rename ABI.

        Parameters
        ----------
        library
            Native library preserving the calling thread's errno.

        Raises
        ------
        OSError
            If the required symbol is absent.
        """
        try:
            self._rename = library.renameat2
        except AttributeError as error:
            message = "report publication requires Linux renameat2(RENAME_NOREPLACE)"
            raise OSError(errno.ENOTSUP, message) from error
        self._rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        self._rename.restype = ctypes.c_int

    def check(self, parent: Path) -> None:
        """Exercise the primitive on the target filesystem before report staging.

        Parameters
        ----------
        parent
            Existing parent of the future report directory.

        Raises
        ------
        OSError
            If native publication or filesystem access is unavailable. The
            capability directory is removed on both success and failure.
        """
        with tempfile.TemporaryDirectory(prefix=".report-publication-probe.", dir=parent) as name:
            probe = Path(name)
            source = probe / "source"
            source.mkdir()
            self.publish(source, probe / "destination")

    def publish(self, source: Path, target: Path) -> None:
        """Atomically move a staged directory while preserving any existing target.

        Parameters
        ----------
        source
            Complete staged directory on the target filesystem.
        target
            Destination path, which must be absent at the native operation.

        Raises
        ------
        OSError
            If the kernel refuses the operation, including an existing target.
        """
        result = self._rename(
            AT_FDCWD, os.fsencode(source), AT_FDCWD, os.fsencode(target), RENAME_NOREPLACE
        )
        if result != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))


def publish_report_directory(output_directory: Path, files: Mapping[str, bytes]) -> None:
    """Create a new report directory only after every file is staged.

    Parameters
    ----------
    output_directory
        New directory for the report. It must not already exist and its
        parent must exist.
    files
        Complete report contents keyed by file name inside the directory.

    Raises
    ------
    FileExistsError
        If the output path already exists, including as a dangling symlink.
    FileNotFoundError
        If the parent directory does not exist.
    OSError
        If Linux atomic publication is unavailable, a file cannot be staged
        or the transaction cannot land. The staging directory is removed and
        an existing destination is never replaced.
    """
    target = output_directory.parent.resolve() / output_directory.name
    if os.path.lexists(target):
        message = f"report directory already exists: {target}"
        raise FileExistsError(message)
    parent = target.parent
    if not parent.is_dir():
        message = f"report parent does not exist: {parent}"
        raise FileNotFoundError(message)
    publication = DirectoryPublication(ctypes.CDLL(None, use_errno=True))
    publication.check(parent)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
    try:
        for name, content in files.items():
            (staging / name).write_bytes(content)
        publication.publish(staging, target)
    except BaseException:
        shutil.rmtree(staging)
        raise
