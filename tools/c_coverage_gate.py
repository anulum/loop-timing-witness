# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete GCC-counted C and C++ line and branch coverage

"""Require every line and branch of the judged C and C++ sources to be executed.

The reports are ``gcov --json-format --stdout --branch-probabilities`` documents
of GCC ``--coverage`` builds. One source compiled into several programs appears
in several reports; their counts are added line by line and branch by branch,
and the same line must carry the same branches in every report.

``--sources DIR`` judges every file under a directory and requires each ``.c``
file directly in it to be measured, so a new file cannot pass unmeasured.
``--source FILE`` judges one named file, such as a C++ header, which must be
measured as well. Files outside the judged set, such as test drivers, are not
judged.

GCC adds an exception edge at every C++ call that may throw. Those edges are
counted and reported but not required. A reviewed list may name branch outcomes
that no real surface can reach, each with its condition and reason, and the
lines that only those outcomes reach; the branch outcomes on those lines are not
required either. A listed outcome or line that runs fails the gate, so the list
cannot go stale.
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
REVIEW_KEYS: Final = frozenset({"file", "line", "outcome", "condition", "reason", "lines"})


@dataclass
class SourceCounts:
    """Execution counts of one source accumulated over every report.

    Attributes
    ----------
    lines
        Execution count of each executable line.
    branches
        Execution count of each branch outcome, in gcov order, per line.
    exceptional
        Whether each branch outcome is a C++ exception edge, per line.
    """

    lines: dict[int, int] = field(default_factory=dict)
    branches: dict[int, list[int]] = field(default_factory=dict)
    exceptional: dict[int, list[bool]] = field(default_factory=dict)


@dataclass(frozen=True)
class Selection:
    """The judged sources: whole directories and individually named files.

    Attributes
    ----------
    directories
        Resolved directories whose files are judged under their relative paths.
    files
        Resolved named files and the name each is reported under.
    """

    directories: tuple[Path, ...] = ()
    files: dict[Path, str] = field(default_factory=dict)

    @classmethod
    def of(cls, directories: Iterable[Path] = (), files: Iterable[Path] = ()) -> Selection:
        """Resolve directories and named files into a selection.

        Parameters
        ----------
        directories
            Directories whose files are judged.
        files
            Named files, reported under their path as given.

        Returns
        -------
        Selection
            The resolved selection.
        """
        return cls(
            tuple(directory.resolve() for directory in directories),
            {path.resolve(): path.as_posix() for path in files},
        )

    def name(self, path: Path) -> str | None:
        """Return the reported name of a resolved source path, if it is judged.

        Parameters
        ----------
        path
            Resolved source path from a report.

        Returns
        -------
        str | None
            The reported name, or ``None`` for a source outside the selection.
        """
        if path in self.files:
            return self.files[path]
        for directory in self.directories:
            if path.is_relative_to(directory):
                return path.relative_to(directory).as_posix()
        return None

    def expected(self) -> set[str]:
        """Return the names that must be measured.

        Returns
        -------
        set[str]
            Every ``.c`` file directly in a judged directory and every named file.
        """
        names = {path.name for directory in self.directories for path in directory.glob("*.c")}
        return names | set(self.files.values())


@dataclass(frozen=True)
class Reviewed:
    """One branch outcome that no real surface can reach, with its reason.

    Attributes
    ----------
    file
        Reported name of the source.
    line
        Line carrying the branch.
    outcome
        Position of the outcome in gcov's branch list of that line.
    condition
        The source condition the outcome would make true.
    reason
        Why no real surface reaches it.
    lines
        Executable lines that only this outcome reaches.
    """

    file: str
    line: int
    outcome: int
    condition: str
    reason: str
    lines: tuple[int, ...]


class CoverageError(ValueError):
    """A report or reviewed list that cannot be used."""


def _add_line(counts: SourceCounts, name: str, line: dict[str, Any]) -> None:
    """Add one gcov line record to the accumulated counts of its source.

    Parameters
    ----------
    counts
        Accumulated counts of the source.
    name
        Reported source name, for messages.
    line
        One ``lines`` element of a gcov file record.

    Raises
    ------
    CoverageError
        If the line carries different branches than before.
    """
    number = int(line["line_number"])
    outcomes = [int(branch["count"]) for branch in line["branches"]]
    exceptional = [bool(branch.get("throw", False)) for branch in line["branches"]]
    counts.lines[number] = counts.lines.get(number, 0) + int(line["count"])
    previous = counts.branches.setdefault(number, [0] * len(outcomes))
    kinds = counts.exceptional.setdefault(number, exceptional)
    if len(previous) != len(outcomes) or kinds != exceptional:
        message = f"{name}:{number}: branch structure differs between reports"
        raise CoverageError(message)
    counts.branches[number] = [
        total + count for total, count in zip(previous, outcomes, strict=True)
    ]


def combine(reports: Iterable[dict[str, Any]], selection: Selection) -> dict[str, SourceCounts]:
    """Add the counts of every report for the judged sources.

    Parameters
    ----------
    reports
        Decoded gcov JSON documents.
    selection
        The judged sources.

    Returns
    -------
    dict[str, SourceCounts]
        Accumulated counts keyed by reported name.

    Raises
    ------
    CoverageError
        If a report has another format or its branch structure differs.
    """
    combined: dict[str, SourceCounts] = {}
    for report in reports:
        files = report.get("files")
        if report.get("format_version") != FORMAT_VERSION or not isinstance(files, list):
            raise CoverageError(UNSUPPORTED)
        for record in files:
            base = Path(report.get("current_working_directory", "."))
            name = selection.name((base / record["file"]).resolve())
            if name is None:
                continue
            counts = combined.setdefault(name, SourceCounts())
            for line in record["lines"]:
                _add_line(counts, name, line)
    return combined


def _review_entry(entry: object, index: int) -> Reviewed:
    """Decode one reviewed-list entry and refuse any malformed field.

    Parameters
    ----------
    entry
        One element of the list's ``entries`` array.
    index
        Its position, for messages.

    Returns
    -------
    Reviewed
        The decoded entry.

    Raises
    ------
    CoverageError
        If the entry has other keys or a field of the wrong kind.
    """
    where = f"reviewed entry {index}"
    if not isinstance(entry, dict) or set(entry) != REVIEW_KEYS:
        message = f"{where}: needs exactly the keys {', '.join(sorted(REVIEW_KEYS))}"
        raise CoverageError(message)
    texts = [entry[key] for key in ("file", "condition", "reason")]
    lines = entry["lines"]
    numbers = [entry["line"], entry["outcome"], *(lines if isinstance(lines, list) else [None])]
    if not all(isinstance(text, str) and text.strip() for text in texts) or not all(
        type(number) is int and number >= 0 for number in numbers
    ):
        message = f"{where}: needs non-empty texts and non-negative integer lines and outcome"
        raise CoverageError(message)
    return Reviewed(
        entry["file"],
        entry["line"],
        entry["outcome"],
        entry["condition"],
        entry["reason"],
        tuple(entry["lines"]),
    )


def load_reviewed(path: Path) -> tuple[Reviewed, ...]:
    """Read a reviewed list of unreachable branch outcomes.

    Parameters
    ----------
    path
        JSON document ``{"entries": [...]}``.

    Returns
    -------
    tuple[Reviewed, ...]
        Its entries in file order.

    Raises
    ------
    CoverageError
        If the document or an entry is malformed or an outcome is listed twice.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        message = f"{path}: not JSON ({error.msg})"
        raise CoverageError(message) from error
    if (
        not isinstance(document, dict)
        or set(document) != {"entries"}
        or not isinstance(document["entries"], list)
    ):
        message = f"{path}: a reviewed list holds only an entries array"
        raise CoverageError(message)
    reviewed = tuple(_review_entry(entry, index) for index, entry in enumerate(document["entries"]))
    keys = [(entry.file, entry.line, entry.outcome) for entry in reviewed]
    if len(set(keys)) != len(keys):
        message = f"{path}: an outcome is listed twice"
        raise CoverageError(message)
    return reviewed


def _stale(combined: dict[str, SourceCounts], entry: Reviewed) -> list[str]:
    """Return why a reviewed entry no longer describes an unreachable outcome.

    Parameters
    ----------
    combined
        Accumulated counts from :func:`combine`.
    entry
        One reviewed entry.

    Returns
    -------
    list[str]
        Missing sources, lines or outcomes, exception edges, and listed outcomes or lines
        that ran; empty when the entry still holds.
    """
    where = f"{entry.file}:{entry.line}"
    counts = combined.get(entry.file)
    if counts is None:
        return [f"{where}: reviewed entry for a source that is not judged"]
    outcomes = counts.branches.get(entry.line, [])
    if entry.outcome >= len(outcomes):
        return [f"{where}: reviewed outcome {entry.outcome} does not exist"]
    if counts.exceptional[entry.line][entry.outcome]:
        return [f"{where}: reviewed outcome {entry.outcome} is an exception edge"]
    result = []
    if outcomes[entry.outcome]:
        result.append(f"{where}: reviewed outcome {entry.outcome} ran ({entry.condition})")
    for number in entry.lines:
        if number not in counts.lines:
            result.append(f"{entry.file}:{number}: reviewed line is not executable")
        elif counts.lines[number]:
            result.append(f"{entry.file}:{number}: reviewed line ran ({entry.condition})")
    return result


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


def _required(
    name: str, counts: SourceCounts, reviewed: Sequence[Reviewed]
) -> tuple[dict[int, int], list[tuple[int, int]]]:
    """Return the line counts and outcome counts a source must cover.

    Parameters
    ----------
    name
        Reported source name.
    counts
        Its accumulated counts.
    reviewed
        Every reviewed entry.

    Returns
    -------
    tuple[dict[int, int], list[tuple[int, int]]]
        Required line counts, and the line number and count of every required outcome:
        exception edges, reviewed outcomes, reviewed lines and the outcomes on those lines
        are excluded.
    """
    lines = {number for entry in reviewed if entry.file == name for number in entry.lines}
    outcomes = {(entry.line, entry.outcome) for entry in reviewed if entry.file == name}
    required_lines = {
        number: count for number, count in counts.lines.items() if number not in lines
    }
    required_outcomes = [
        (number, count)
        for number, line in sorted(counts.branches.items())
        if number not in lines
        for outcome, count in enumerate(line)
        if not counts.exceptional[number][outcome] and (number, outcome) not in outcomes
    ]
    return required_lines, required_outcomes


def findings(
    combined: dict[str, SourceCounts], selection: Selection, reviewed: Sequence[Reviewed] = ()
) -> list[str]:
    """Return every reason the combined counts do not cover the judged sources.

    Parameters
    ----------
    combined
        Accumulated counts from :func:`combine`.
    selection
        The judged sources.
    reviewed
        Branch outcomes accepted as unreachable, with their lines.

    Returns
    -------
    list[str]
        Unmeasured sources, stale reviewed entries and sources with unexecuted required
        lines or untaken required outcomes; empty when coverage is complete.
    """
    result = [f"{name}: not measured" for name in sorted(selection.expected() - set(combined))]
    for entry in reviewed:
        result.extend(_stale(combined, entry))
    for name, counts in sorted(combined.items()):
        lines, outcomes = _required(name, counts, reviewed)
        missed_lines = [number for number, count in sorted(lines.items()) if count == 0]
        if missed_lines:
            covered = len(lines) - len(missed_lines)
            result.append(
                f"{name}: lines {covered}/{len(lines)}, unexecuted {_uncovered(missed_lines)}"
            )
        missed_branches = sorted({number for number, count in outcomes if count == 0})
        if missed_branches:
            covered = sum(count > 0 for _, count in outcomes)
            result.append(
                f"{name}: branches {covered}/{len(outcomes)}, "
                f"untaken on lines {_uncovered(missed_branches)}"
            )
    return result


def summary(combined: dict[str, SourceCounts], reviewed: Sequence[Reviewed] = ()) -> str:
    """Describe complete coverage: required totals, reviewed exclusions, exception edges.

    Parameters
    ----------
    combined
        Accumulated counts from :func:`combine`, already free of findings.
    reviewed
        The reviewed entries the gate applied.

    Returns
    -------
    str
        The pass line's totals.
    """
    required = [_required(name, counts, reviewed) for name, counts in combined.items()]
    lines = sum(len(line_counts) for line_counts, _ in required)
    branches = sum(len(outcomes) for _, outcomes in required)
    text = f"lines {lines}/{lines}, branches {branches}/{branches}"
    edges = [
        count
        for counts in combined.values()
        for number, line in counts.branches.items()
        for outcome, count in enumerate(line)
        if counts.exceptional[number][outcome]
    ]
    if reviewed:
        executable = sum(len(counts.lines) for counts in combined.values())
        outcomes = sum(
            len(line) for counts in combined.values() for line in counts.branches.values()
        )
        text += (
            f"; reviewed unreachable: lines {executable - lines}, "
            f"branch outcomes {outcomes - len(edges) - branches}"
        )
    if edges:
        taken = sum(count > 0 for count in edges)
        text += f"; exception edges taken {taken}/{len(edges)}, not required"
    return text


def main(argv: Sequence[str] | None = None) -> int:
    """Check the gcov reports against the judged sources.

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
    parser.add_argument("--sources", type=Path, action="append", default=[])
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--reviewed", type=Path)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if not args.sources and not args.source:
        parser.error("name at least one --sources directory or --source file")
    selection = Selection.of(args.sources, args.source)
    combined: dict[str, SourceCounts] = {}
    reviewed: tuple[Reviewed, ...] = ()
    try:
        reviewed = load_reviewed(args.reviewed) if args.reviewed else ()
        combined = combine(
            (json.loads(path.read_text(encoding="utf-8")) for path in args.reports), selection
        )
        failures = findings(combined, selection, reviewed)
    except CoverageError as error:
        failures = [str(error)]
    if failures:
        for failure in failures:
            print(f"GCC coverage: FAIL {failure}", file=sys.stderr)
        return 2
    print(f"GCC coverage: PASS {summary(combined, reviewed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
