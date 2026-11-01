# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete C controller line and branch coverage

"""Require every line and branch of every C source in one directory to be executed.

The reports are ``gcov --json-format --stdout --branch-probabilities`` documents
of GCC ``--coverage`` builds. One source compiled into several programs appears
in several reports; their counts are added line by line and branch by branch,
and the same line must carry the same number of branches in every report.
Every ``.c`` file directly in the source directory must be measured, so a new
file cannot pass unmeasured. Files outside that directory, such as test
drivers, are not judged.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

FORMAT_VERSION: Final = "1"
UNSUPPORTED: Final = "Unsupported gcov report."
SHOWN_LINES: Final = 10


@dataclass
class SourceCounts:
    """Execution counts of one source accumulated over every report.

    Attributes
    ----------
    lines
        Execution count of each executable line.
    branches
        Execution count of each branch outcome, in gcov order, per line.
    """

    lines: dict[int, int] = field(default_factory=dict)
    branches: dict[int, list[int]] = field(default_factory=dict)


class CoverageError(ValueError):
    """A report that cannot be combined with the others."""


def _add_line(counts: SourceCounts, name: str, line: dict[str, Any]) -> None:
    """Add one gcov line record to the accumulated counts of its source.

    Parameters
    ----------
    counts
        Accumulated counts of the source.
    name
        Source path relative to the source directory, for messages.
    line
        One ``lines`` element of a gcov file record.

    Raises
    ------
    CoverageError
        If the line carries a different number of branches than before.
    """
    number = int(line["line_number"])
    outcomes = [int(branch["count"]) for branch in line["branches"]]
    counts.lines[number] = counts.lines.get(number, 0) + int(line["count"])
    previous = counts.branches.setdefault(number, [0] * len(outcomes))
    if len(previous) != len(outcomes):
        message = f"{name}:{number}: branch structure differs between reports"
        raise CoverageError(message)
    counts.branches[number] = [
        total + count for total, count in zip(previous, outcomes, strict=True)
    ]


def combine(reports: Iterable[dict[str, Any]], sources: Path) -> dict[str, SourceCounts]:
    """Add the counts of every report for the sources in one directory.

    Parameters
    ----------
    reports
        Decoded gcov JSON documents.
    sources
        Directory whose C sources are judged.

    Returns
    -------
    dict[str, SourceCounts]
        Accumulated counts keyed by path relative to ``sources``.

    Raises
    ------
    CoverageError
        If a report has another format or its branch structure differs.
    """
    root = sources.resolve()
    combined: dict[str, SourceCounts] = {}
    for report in reports:
        files = report.get("files")
        if report.get("format_version") != FORMAT_VERSION or not isinstance(files, list):
            raise CoverageError(UNSUPPORTED)
        for record in files:
            base = Path(report.get("current_working_directory", "."))
            path = (base / record["file"]).resolve()
            if not path.is_relative_to(root):
                continue
            name = path.relative_to(root).as_posix()
            counts = combined.setdefault(name, SourceCounts())
            for line in record["lines"]:
                _add_line(counts, name, line)
    return combined


def _uncovered(numbers: Iterable[int]) -> str:
    """Name the first uncovered line numbers.

    Parameters
    ----------
    numbers
        Uncovered line numbers in ascending order.

    Returns
    -------
    str
        Comma-separated numbers, ending with an ellipsis when more exist.
    """
    listed = list(numbers)
    shown = ", ".join(str(number) for number in listed[:SHOWN_LINES])
    return shown + (", …" if len(listed) > SHOWN_LINES else "")


def findings(combined: dict[str, SourceCounts], sources: Path) -> list[str]:
    """Return every reason the combined counts do not cover the sources completely.

    Parameters
    ----------
    combined
        Accumulated counts from :func:`combine`.
    sources
        Directory whose ``.c`` files must all be measured.

    Returns
    -------
    list[str]
        Unmeasured files and files with unexecuted lines or branches; empty
        when coverage is complete.
    """
    expected = {path.name for path in sources.glob("*.c")}
    result = [f"{name}: not measured" for name in sorted(expected - set(combined))]
    for name, counts in sorted(combined.items()):
        missed_lines = [number for number, count in sorted(counts.lines.items()) if count == 0]
        if missed_lines:
            covered = len(counts.lines) - len(missed_lines)
            result.append(
                f"{name}: lines {covered}/{len(counts.lines)}, "
                f"unexecuted {_uncovered(missed_lines)}"
            )
        outcomes = [count for line in counts.branches.values() for count in line]
        missed_branches = [number for number, line in sorted(counts.branches.items()) if 0 in line]
        if missed_branches:
            covered = sum(count > 0 for count in outcomes)
            result.append(
                f"{name}: branches {covered}/{len(outcomes)}, "
                f"untaken on lines {_uncovered(missed_branches)}"
            )
    return result


def totals(combined: dict[str, SourceCounts]) -> tuple[int, int]:
    """Return the number of executable lines and of branch outcomes.

    Parameters
    ----------
    combined
        Accumulated counts from :func:`combine`.

    Returns
    -------
    tuple[int, int]
        Line and branch totals over every judged source.
    """
    lines = sum(len(counts.lines) for counts in combined.values())
    branches = sum(len(line) for counts in combined.values() for line in counts.branches.values())
    return lines, branches


def main(argv: Sequence[str] | None = None) -> int:
    """Check the gcov reports against one C source directory.

    Parameters
    ----------
    argv
        Command arguments; defaults to this process's arguments.

    Returns
    -------
    int
        Zero when coverage is complete, two otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args(argv)
    combined: dict[str, SourceCounts] = {}
    try:
        combined = combine(
            (json.loads(path.read_text(encoding="utf-8")) for path in args.reports), args.sources
        )
        failures = findings(combined, args.sources)
    except CoverageError as error:
        failures = [str(error)]
    if failures:
        for failure in failures:
            print(f"C coverage: FAIL {failure}", file=sys.stderr)
        return 2
    lines, branches = totals(combined)
    print(f"C coverage: PASS lines {lines}/{lines}, branches {branches}/{branches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
