# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared test configuration

"""Shared test configuration.

The stand-alone modules under ``tools/`` run as ``python tools/<name>.py``,
which puts ``tools/`` first on the import path; the tests import them the
same way. The fixtures run tools as real subprocesses and create real Git
work trees.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY_ROOT / "tools"))

RunTool = Callable[..., subprocess.CompletedProcess[str]]
MakeGitTree = Callable[[dict[str, str | bytes]], Path]


@pytest.fixture
def run_tool() -> RunTool:
    """Return a runner that executes one repository tool as a subprocess.

    Returns
    -------
    RunTool
        ``run(tool_name, *arguments)`` runs ``python tools/<tool_name>.py``
        from the repository root with the current interpreter and returns the
        completed process with captured text output.
    """

    def run(tool: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "tools" / f"{tool}.py"), *arguments],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    return run


@pytest.fixture
def make_git_tree(tmp_path: Path) -> MakeGitTree:
    """Return a factory for Git work trees populated with given files.

    Parameters
    ----------
    tmp_path
        Pytest-provided scratch directory.

    Returns
    -------
    MakeGitTree
        ``make(files)`` initialises a Git repository in a new directory,
        writes each relative path with its text or bytes, and returns the
        work-tree root. Nothing is staged or committed.
    """
    counter = 0

    def make(files: dict[str, str | bytes]) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"tree-{counter}"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        return root

    return make
