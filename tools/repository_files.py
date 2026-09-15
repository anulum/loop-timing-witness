# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — publishable file listing from Git

"""List the files a commit of this work tree could publish.

The listing is every tracked file plus every untracked file that Git does not
ignore. Guards that run on this set see a new file before it is staged and
never see ignored private or generated content such as ``docs/internal/`` or
the virtual environment.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def candidate_files(root: Path) -> list[str]:
    """List tracked and non-ignored untracked files of one Git work tree.

    Parameters
    ----------
    root
        Work-tree root.

    Returns
    -------
    list[str]
        POSIX paths relative to ``root``, sorted, limited to regular files
        that exist on disk.

    Raises
    ------
    RuntimeError
        If Git cannot be executed or cannot list the work tree.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        message = f"cannot run git in {root}: {exc}"
        raise RuntimeError(message) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        message = f"git ls-files failed in {root}: {detail}"
        raise RuntimeError(message)
    names = {name for name in completed.stdout.decode("utf-8").split("\0") if name}
    return sorted(name for name in names if (root / name).is_file())
