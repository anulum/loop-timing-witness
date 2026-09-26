# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — provenance header and rendered-Markdown guard

"""Fail closed when a repository file lacks the seven-line provenance header.

The candidate set is every tracked file plus every untracked file that Git
does not ignore, so a new file is checked before it is staged. Each file type
has exactly one rule:

- hash-comment files (Python, TOML, YAML, requirements, citation metadata,
  Makefile and Git/editor configuration) start with the seven header lines,
  each prefixed by ``# ``; Python files may carry a shebang line first;
- SystemVerilog files start with the same seven lines prefixed by ``// ``;
- Markdown files start with an HTML comment that holds the seven lines, so the
  rendered page starts with content and never shows a code-style header;
- JSON, PDF and licence files cannot carry the text header and are exempt; their
  licensing is declared in ``REUSE.toml`` and verified by ``reuse lint``.

A file type without a rule is itself a finding: the guard never skips a file
it does not understand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath
from typing import Final

from repository_files import candidate_files

# The expected header text below is data, not this file's licence statement;
# the REUSE markers keep the licensing tool from reading it as one.
# REUSE-IgnoreStart
HEADER_LINES: Final = (
    "SPDX-License-Identifier: AGPL-3.0-or-later",
    "Commercial license available",
    "© Concepts 1996–2026 Miroslav Šotek. All rights reserved.",
    "© Code 2020–2026 Miroslav Šotek. All rights reserved.",
    "ORCID: 0009-0009-3560-0851",
    "Contact: www.anulum.li | protoscience@anulum.li",
)
# REUSE-IgnoreEnd
TITLE_PREFIX: Final = "Loop Timing Witness — "
HASH_COMMENT_SUFFIXES: Final = frozenset({".cff", ".in", ".py", ".toml", ".txt", ".yaml", ".yml"})
HASH_COMMENT_NAMES: Final = frozenset(
    {".editorconfig", ".gitattributes", ".gitignore", "CODEOWNERS", "Makefile"}
)
SLASH_COMMENT_SUFFIXES: Final = frozenset({".sv", ".svh"})
EXEMPT_SUFFIXES: Final = frozenset({".json", ".pdf"})
EXEMPT_PATHS: Final = frozenset({"LICENSE"})
EXEMPT_DIRECTORIES: Final = frozenset({"LICENSES"})


def _title_finding(relative: str, line: str) -> str | None:
    """Check the seventh, project-specific header line.

    Parameters
    ----------
    relative
        File path for the finding.
    line
        Seventh header line without its comment prefix.

    Returns
    -------
    str or None
        A finding, or ``None`` when the line names the project and a file
        description.
    """
    if not line.startswith(TITLE_PREFIX) or not line.removeprefix(TITLE_PREFIX).strip():
        return f"{relative}: header line 7 must read '{TITLE_PREFIX}<description>'"
    return None


def _line_comment_finding(relative: str, lines: list[str], marker: str) -> str | None:
    """Check a hash- or slash-comment provenance header.

    Parameters
    ----------
    relative
        File path for the finding.
    lines
        File lines.
    marker
        ``#`` or ``//``.

    Returns
    -------
    str or None
        A finding, or ``None`` when the header is complete.
    """
    body = (
        lines[1:]
        if marker == "#" and relative.endswith(".py") and lines[:1] and lines[0].startswith("#!")
        else lines
    )
    expected = [f"{marker} {text}" for text in HEADER_LINES]
    if body[: len(expected)] != expected or len(body) <= len(expected):
        return f"{relative}: must start with the seven-line '{marker} ' provenance header"
    return _title_finding(relative, body[len(expected)].removeprefix(f"{marker} "))


def _markdown_finding(relative: str, lines: list[str]) -> str | None:
    """Check a Markdown header held inside an HTML comment.

    Parameters
    ----------
    relative
        File path for the finding.
    lines
        File lines.

    Returns
    -------
    str or None
        A finding, or ``None`` when the comment holds the header and content
        follows it.
    """
    count = len(HEADER_LINES)
    if (
        lines[:1] != ["<!--"]
        or lines[1 : count + 1] != list(HEADER_LINES)
        or len(lines) < count + 3
        or lines[count + 2] != "-->"
    ):
        return f"{relative}: must start with the provenance header inside '<!--' and '-->'"
    title = _title_finding(relative, lines[count + 1])
    if title is not None:
        return title
    if not any(line.strip() for line in lines[count + 3 :]):
        return f"{relative}: no rendered content follows the provenance comment"
    return None


def file_finding(root: Path, relative: str) -> str | None:
    """Apply the rule for one file's type.

    Parameters
    ----------
    root
        Work-tree root.
    relative
        POSIX path relative to ``root``.

    Returns
    -------
    str or None
        A finding, or ``None`` when the file complies or is exempt.
    """
    path = PurePosixPath(relative)
    if (
        relative in EXEMPT_PATHS
        or path.parts[0] in EXEMPT_DIRECTORIES
        or path.suffix in EXEMPT_SUFFIXES
    ):
        return None
    try:
        text = (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{relative}: unreadable as UTF-8 text: {exc}"
    lines = text.splitlines()
    if path.suffix == ".md":
        return _markdown_finding(relative, lines)
    if path.suffix in HASH_COMMENT_SUFFIXES or path.name in HASH_COMMENT_NAMES:
        return _line_comment_finding(relative, lines, "#")
    if path.suffix in SLASH_COMMENT_SUFFIXES:
        return _line_comment_finding(relative, lines, "//")
    return f"{relative}: no provenance rule for this file type"


def audit(root: Path) -> list[str]:
    """Check every candidate file of one work tree.

    Parameters
    ----------
    root
        Work-tree root.

    Returns
    -------
    list[str]
        Findings in path order; empty when every file complies.
    """
    try:
        files = candidate_files(root)
    except RuntimeError as exc:
        return [str(exc)]
    return [finding for relative in files if (finding := file_finding(root, relative)) is not None]


def main(argv: list[str] | None = None) -> int:
    """Run the provenance header guard.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when every file complies, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1],
        help="work-tree root (default: the repository containing this tool)",
    )
    args = parser.parse_args(argv)
    findings = audit(args.root)
    for finding in findings:
        print(f"provenance-headers: FAIL {finding}")
    if findings:
        return 1
    print("provenance-headers: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
