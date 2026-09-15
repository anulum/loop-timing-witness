# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — documentation link and anchor integrity guard

"""Fail closed when published Markdown links to something a reader cannot reach.

The guard reads every publishable Markdown file (tracked or untracked and not
ignored by Git) and checks, outside fenced code blocks and inline code spans:

- the file decodes as UTF-8;
- every relative inline link, image and reference definition resolves to a
  publishable file, or to a directory that contains one, inside the
  repository; a target in an ignored path such as ``docs/internal/`` is
  broken for every reader of the published repository and is a finding;
- every fragment that points into a Markdown file names a heading of that
  file, using the heading identifiers GitHub generates.

External ``http``, ``https`` and ``mailto`` targets are not fetched; the
guard is deterministic and needs no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Final
from urllib.parse import unquote

from repository_files import candidate_files

FENCE: Final = re.compile(r"^\s*(```|~~~)")
INLINE_CODE: Final = re.compile(r"`[^`]*`")
INLINE_LINK: Final = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE_DEFINITION: Final = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
EXTERNAL: Final = re.compile(r"^(https?:|mailto:)", re.IGNORECASE)
HEADING: Final = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
NOT_SLUG_CHARACTER: Final = re.compile(r"[^\w\- ]")


def unfenced_lines(text: str) -> list[str]:
    """Return the lines of a Markdown document with fenced code blanked out.

    Parameters
    ----------
    text
        Markdown source.

    Returns
    -------
    list[str]
        One entry per source line; fence delimiters and fenced content are
        empty strings, so line numbers are preserved.
    """
    result = []
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            result.append("")
        else:
            result.append("" if fenced else line)
    return result


def heading_anchors(text: str) -> set[str]:
    """Return the fragment identifiers GitHub generates for a document's headings.

    Parameters
    ----------
    text
        Markdown source.

    Returns
    -------
    set[str]
        Lowercased heading text with punctuation other than hyphens and
        underscores removed and spaces turned into hyphens; a repeated
        identifier gains ``-1``, ``-2`` and so on.
    """
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in unfenced_lines(text):
        match = HEADING.match(line.replace("`", ""))
        if match is None:
            continue
        base = NOT_SLUG_CHARACTER.sub("", match.group(1).lower()).replace(" ", "-")
        seen = counts.get(base, 0)
        anchors.add(base if seen == 0 else f"{base}-{seen}")
        counts[base] = seen + 1
    return anchors


def link_targets(text: str) -> list[tuple[int, str]]:
    """Extract link targets with their one-based line numbers.

    Parameters
    ----------
    text
        Markdown source.

    Returns
    -------
    list[tuple[int, str]]
        Inline link, image and reference-definition targets in document
        order.
    """
    targets: list[tuple[int, str]] = []
    for number, raw_line in enumerate(unfenced_lines(text), start=1):
        line = INLINE_CODE.sub("", raw_line)
        targets.extend((number, match.group(1)) for match in INLINE_LINK.finditer(line))
        definition = REFERENCE_DEFINITION.match(line)
        if definition is not None:
            targets.append((number, definition.group(1)))
    return targets


def _target_finding(
    source: str,
    number: int,
    target: str,
    publishable: set[str],
    documents: dict[str, str],
) -> str | None:
    """Check one link target.

    Parameters
    ----------
    source
        Relative path of the Markdown file holding the link.
    number
        Line number of the link.
    target
        Raw link target.
    publishable
        Publishable relative file paths.
    documents
        Text of every readable publishable Markdown file by path.

    Returns
    -------
    str or None
        A finding, or ``None`` when the target is external or reachable.
    """
    if EXTERNAL.match(target):
        return None
    location = f"{source}:{number}"
    path_part, _, fragment = target.partition("#")
    path_part = unquote(path_part)
    if path_part.startswith("/"):
        return f"{location}: absolute link {target!r} does not resolve on every host"
    if path_part:
        # PurePosixPath already drops "." segments; only ".." needs resolving.
        joined = PurePosixPath(source).parent / path_part
        parts: list[str] = []
        for part in joined.parts:
            if part != "..":
                parts.append(part)
            elif parts:
                parts.pop()
            else:
                return f"{location}: link {target!r} leaves the repository"
        resolved = "/".join(parts)
    else:
        resolved = source
    is_file = resolved in publishable
    is_directory = any(name.startswith(f"{resolved}/") for name in publishable)
    if not (is_file or is_directory):
        return f"{location}: link {target!r} does not reach a publishable path"
    if (
        fragment
        and resolved in documents
        and unquote(fragment).lower() not in heading_anchors(documents[resolved])
    ):
        return f"{location}: fragment {fragment!r} names no heading of {resolved}"
    return None


def audit(root: Path) -> list[str]:
    """Check every publishable Markdown file of one work tree.

    Parameters
    ----------
    root
        Work-tree root.

    Returns
    -------
    list[str]
        Findings in file and line order; empty when every link resolves.
    """
    try:
        publishable = set(candidate_files(root))
    except RuntimeError as exc:
        return [str(exc)]
    findings = []
    documents: dict[str, str] = {}
    for source in sorted(name for name in publishable if name.endswith(".md")):
        try:
            documents[source] = (root / source).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{source}: unreadable as UTF-8: {exc}")
    for source, text in documents.items():
        for number, target in link_targets(text):
            finding = _target_finding(source, number, target, publishable, documents)
            if finding is not None:
                findings.append(finding)
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the documentation guard.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when every link resolves, ``1`` otherwise.
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
        print(f"documentation: FAIL {finding}")
    if findings:
        return 1
    print("documentation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
