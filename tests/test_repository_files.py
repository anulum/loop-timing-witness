# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the publishable file listing

"""Contract tests for the publishable-file listing taken from Git."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT, MakeGitTree
from repository_files import candidate_files

if TYPE_CHECKING:
    from pathlib import Path


def test_listing_holds_tracked_and_untracked_but_not_ignored_files(
    make_git_tree: MakeGitTree,
) -> None:
    """Tracked and new files are listed; ignored and deleted files are not."""
    root = make_git_tree(
        {
            ".gitignore": "docs/internal/\n*.log\n",
            "README.md": "readme",
            "docs/guide.md": "guide",
            "docs/internal/private.md": "private",
            "run.log": "log",
            "gone.txt": "tracked then deleted",
        }
    )
    subprocess.run(["git", "add", ".gitignore", "README.md", "gone.txt"], cwd=root, check=True)
    (root / "gone.txt").unlink()
    assert candidate_files(root) == [".gitignore", "README.md", "docs/guide.md"]


def test_listing_of_the_repository_excludes_private_and_environment_paths() -> None:
    """The repository's own listing never contains ignored trees."""
    files = candidate_files(REPOSITORY_ROOT)
    assert "measurement-domain.json" in files
    assert not [name for name in files if name.startswith((".venv/", "docs/internal/"))]


def test_directory_outside_git_raises(tmp_path: Path) -> None:
    """A directory that is not a work tree is an error, not an empty listing."""
    outside = tmp_path / "plain"
    outside.mkdir()
    with pytest.raises(RuntimeError, match="git ls-files failed"):
        candidate_files(outside)


def test_missing_git_executable_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without Git on the search path the listing fails explicitly."""
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="cannot run git"):
        candidate_files(tmp_path)
