# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete GCC-counted C and C++ coverage gate

"""Combine real GCC coverage reports and accept only complete C and C++ coverage."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from c_coverage_gate import (
    FORMAT_VERSIONS,
    UNSUPPORTED,
    CoverageError,
    Selection,
    combine,
    findings,
    load_reviewed,
    main,
)
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from conftest import RunTool

SOURCE = """\
int choose(int value) {
    if (value > 0) {
        return 1;
    }
    return 2;
}
"""

DRIVER = """\
int choose(int value);
int main(int argc, char **argv) {
    (void)argv;
    (void)choose(argc - 2);
    return 0;
}
"""


def _program(root: Path, name: str, arguments: list[str]) -> Path:
    """Build one GCC coverage program from the shared source, run it and export its report.

    Parameters
    ----------
    root
        Owned directory holding ``sources`` and the program outputs.
    name
        Program name.
    arguments
        Extra command arguments; one argument takes the positive branch.

    Returns
    -------
    Path
        The program's gcov JSON report for the shared source.
    """
    output = root / name
    output.mkdir()
    subprocess.run(
        [
            "gcc",
            "-O0",
            "--coverage",
            "-fprofile-abs-path",
            str(root / "sources/choose.c"),
            str(root / "driver.c"),
            "-o",
            str(output / "program"),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(output / "program"), *arguments], check=True)
    report = subprocess.run(
        [
            "gcov",
            "--json-format",
            "--stdout",
            "--branch-probabilities",
            str(output / "program-choose.gcno"),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=output,
    )
    path = output / "choose.json"
    path.write_text(report.stdout, encoding="utf-8")
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Create a source directory with one C file and an outside driver.

    Parameters
    ----------
    tmp_path
        Owned directory.

    Returns
    -------
    Path
        The owned directory.
    """
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/choose.c").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "driver.c").write_text(DRIVER, encoding="utf-8")
    return tmp_path


def _load(path: Path) -> dict[str, Any]:
    """Decode one report.

    Parameters
    ----------
    path
        gcov JSON report.

    Returns
    -------
    dict[str, Any]
        Decoded document.
    """
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def test_two_real_programs_cover_the_shared_source_only_together(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Add the counts of two programs that each take one branch of the same source.

    Parameters
    ----------
    tree
        Owned source tree.
    capsys
        Captured command output.
    """
    negative = _program(tree, "negative", [])
    positive = _program(tree, "positive", ["take-positive", "branch"])
    sources = Selection.of([tree / "sources"])
    alone = findings(combine([_load(negative)], sources), sources)
    assert len(alone) == 2
    assert alone[0].startswith("choose.c: lines 3/4, unexecuted 3")
    assert alone[1].startswith("choose.c: branches 1/2, untaken on lines 2")
    assert main(["--sources", str(tree / "sources"), str(negative), str(positive)]) == 0
    assert capsys.readouterr().out == "GCC coverage: PASS lines 4/4, branches 2/2\n"


def test_the_driver_outside_the_sources_is_not_judged_and_a_missing_source_fails(
    tree: Path,
) -> None:
    """Ignore the uncovered driver lines and name a source with no report.

    Parameters
    ----------
    tree
        Owned source tree.
    """
    report = _load(_program(tree, "negative", []))
    driver = subprocess.run(
        [
            "gcov",
            "--json-format",
            "--stdout",
            "--branch-probabilities",
            str(tree / "negative/program-driver.gcno"),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=tree / "negative",
    )
    driver_report = json.loads(driver.stdout)
    assert [Path(record["file"]).name for record in driver_report["files"]] == ["driver.c"]
    selection = Selection.of([tree / "sources"])
    combined = combine([report, driver_report], selection)
    assert set(combined) == {"choose.c"}
    (tree / "sources/added.c").write_text("int added(void) { return 0; }\n", encoding="utf-8")
    assert findings(combined, selection)[0] == "added.c: not measured"


def test_unsupported_and_inconsistent_reports_are_refused(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse another report format and a line whose branch structure changed.

    Parameters
    ----------
    tree
        Owned source tree.
    capsys
        Captured command output.
    """
    sources = Selection.of([tree / "sources"])
    for document in ({"format_version": "0", "files": []}, {"format_version": "2"}):
        with pytest.raises(CoverageError, match=UNSUPPORTED):
            combine([document], sources)
    report = _load(_program(tree, "negative", []))
    changed = json.loads(json.dumps(report))
    for line in changed["files"][0]["lines"]:
        line["branches"] = line["branches"][:1]
    with pytest.raises(CoverageError, match=r"choose\.c:2: branch structure differs"):
        combine([report, changed], sources)
    path = tree / "foreign.json"
    path.write_text(json.dumps({"format_version": "0", "files": []}), encoding="utf-8")
    assert main(["--sources", str(tree / "sources"), str(path)]) == 2
    assert capsys.readouterr().err == f"GCC coverage: FAIL {UNSUPPORTED}\n"


def test_a_branchless_record_on_a_branching_line_adds_only_its_count(tree: Path) -> None:
    """Add a record without branches, as a macro's factory function places one, to the count.

    gcov lists a line once for each function with code on it; a branchless record before
    or after the branching one leaves the branches as they are.

    Parameters
    ----------
    tree
        Owned source tree.
    """
    sources = Selection.of([tree / "sources"])
    report = _load(_program(tree, "negative", []))
    plain = combine([report], sources)["choose.c"]
    record = report["files"][0]
    branching = next(line for line in record["lines"] if line["branches"])
    branchless = {**branching, "count": 5, "branches": []}
    record["lines"] = [branchless, *record["lines"], branchless]
    counts = combine([report], sources)["choose.c"]
    number = int(branching["line_number"])
    assert counts.lines[number] == plain.lines[number] + 10
    assert counts.branches == plain.branches
    assert counts.exceptional == plain.exceptional


@pytest.mark.parametrize("version", sorted(FORMAT_VERSIONS))
def test_long_uncovered_ranges_are_shortened(tree: Path, version: str) -> None:
    """List at most ten unexecuted lines and mark the rest, in either gcov JSON format.

    Parameters
    ----------
    tree
        Owned source tree.
    version
        gcov JSON format: 1 from GCC 13, 2 from GCC 14 and later.
    """
    lines = [{"line_number": number, "count": 0, "branches": []} for number in range(1, 13)]
    report = {
        "format_version": version,
        "current_working_directory": str(tree),
        "files": [{"file": str(tree / "sources/choose.c"), "lines": lines}],
    }
    sources = Selection.of([tree / "sources"])
    assert findings(combine([report], sources), sources) == [
        "choose.c: lines 0/12, unexecuted 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, …"
    ]


def test_the_command_reports_through_its_exit_status(tree: Path, run_tool: RunTool) -> None:
    """Run the gate as the build runs it and require its status and message.

    Parameters
    ----------
    tree
        Owned source tree.
    run_tool
        Runs one repository tool in a subprocess.
    """
    report = _program(tree, "negative", [])
    result = run_tool("c_coverage_gate", "--sources", str(tree / "sources"), str(report))
    assert result.returncode == 2
    assert result.stderr.splitlines()[0] == "GCC coverage: FAIL choose.c: lines 3/4, unexecuted 3"


HEADER = """\
#include <stdexcept>
inline int decide(int value) {
    if (value < -100)
        throw std::runtime_error("far below");
    return value > 0 ? 1 : 2;
}
"""

CPP_DRIVER = """\
#include "decide.h"
int main(int argc, char **) { return decide(argc - 2) == 1 ? 0 : 0; }
"""


@pytest.fixture
def header(tmp_path: Path) -> tuple[Path, Path]:
    """Build a C++ header program, run both reachable outcomes and export the report.

    The header refuses a value below -100 with a throw, which ``argc - 2`` never reaches,
    so line 3's first outcome and line 4 stay unexecuted and line 4 carries an exception
    edge.

    Parameters
    ----------
    tmp_path
        Owned directory.

    Returns
    -------
    tuple[Path, Path]
        The judged header and the gcov JSON report of the program.
    """
    (tmp_path / "decide.h").write_text(HEADER, encoding="utf-8")
    (tmp_path / "driver.cpp").write_text(CPP_DRIVER, encoding="utf-8")
    subprocess.run(
        [
            "g++",
            "-O0",
            "--coverage",
            "-fprofile-abs-path",
            str(tmp_path / "driver.cpp"),
            "-o",
            str(tmp_path / "program"),
        ],
        check=True,
        capture_output=True,
    )
    for arguments in ([], ["positive", "value"]):
        subprocess.run([str(tmp_path / "program"), *arguments], check=True)
    report = subprocess.run(
        [
            "gcov",
            "--json-format",
            "--stdout",
            "--branch-probabilities",
            str(tmp_path / "program-driver.gcno"),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    path = tmp_path / "decide.json"
    path.write_text(report.stdout, encoding="utf-8")
    return tmp_path / "decide.h", path


def _review(path: Path, entries: object) -> Path:
    """Write a reviewed list.

    Parameters
    ----------
    path
        Destination file.
    entries
        The ``entries`` value, possibly malformed.

    Returns
    -------
    Path
        The written list.
    """
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def _entry(file: Path, **changes: object) -> dict[str, object]:
    """Return the reviewed entry for the header's unreachable refusal, with changes.

    Parameters
    ----------
    file
        The judged header.
    **changes
        Fields to replace.

    Returns
    -------
    dict[str, object]
        One reviewed entry.
    """
    entry: dict[str, object] = {
        "file": file.as_posix(),
        "line": 3,
        "outcome": 0,
        "condition": "value < -100",
        "reason": "the driver passes argc - 2, at least -1",
        "lines": [4],
    }
    entry.update(changes)
    return entry


def test_a_header_needs_its_reachable_outcomes_and_reports_exception_edges(
    header: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Judge a named C++ header, requiring the throw line until it is reviewed.

    Parameters
    ----------
    header
        The judged header and its report.
    capsys
        Captured command output.
    """
    source, report = header
    selection = Selection.of(files=[source])
    combined = combine([_load(report)], selection)
    assert combined[source.as_posix()].exceptional[4] == [False, True]
    assert findings(combined, selection) == [
        f"{source.as_posix()}: lines 3/4, unexecuted 4",
        f"{source.as_posix()}: branches 3/5, untaken on lines 3, 4",
    ]
    review = _review(source.parent / "review.json", [_entry(source)])
    assert main(["--source", str(source), "--reviewed", str(review), str(report)]) == 0
    assert capsys.readouterr().out == (
        "GCC coverage: PASS lines 3/3, branches 3/3; reviewed unreachable: lines 1, "
        "branch outcomes 2; exception edges taken 0/1, not required\n"
    )
    missing = Selection.of(files=[source.parent / "other.h"])
    assert findings(combine([_load(report)], missing), missing) == [
        f"{(source.parent / 'other.h').as_posix()}: not measured"
    ]


def test_a_reviewed_entry_that_runs_or_does_not_fit_fails(
    header: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse stale entries and entries naming no unexecuted outcome of a judged source.

    Parameters
    ----------
    header
        The judged header and its report.
    capsys
        Captured command output.
    """
    source, report = header
    taken = _load(report)
    for record in taken["files"]:
        for line in record["lines"]:
            if Path(record["file"]).name == "decide.h" and line["line_number"] in (3, 4):
                line["branches"][0]["count"] = 1
                line["count"] = max(int(line["count"]), 1)
    stale = source.parent / "stale.json"
    stale.write_text(json.dumps(taken), encoding="utf-8")
    review = _review(source.parent / "review.json", [_entry(source)])
    assert main(["--source", str(source), "--reviewed", str(review), str(stale)]) == 2
    name = source.as_posix()
    assert capsys.readouterr().err.splitlines() == [
        f"GCC coverage: FAIL {name}:3: reviewed outcome 0 ran (value < -100)",
        f"GCC coverage: FAIL {name}:4: reviewed line ran (value < -100)",
    ]
    unfit = [
        _entry(source.parent / "other.h"),
        _entry(source, line=5, outcome=7),
        _entry(source, line=4, outcome=1),
        _entry(source, lines=[9]),
    ]
    review = _review(source.parent / "unfit.json", unfit)
    assert main(["--source", str(source), "--reviewed", str(review), str(report)]) == 2
    assert capsys.readouterr().err.splitlines()[:4] == [
        (
            f"GCC coverage: FAIL {(source.parent / 'other.h').as_posix()}:3: "
            "reviewed entry for a source that is not judged"
        ),
        f"GCC coverage: FAIL {name}:5: reviewed outcome 7 does not exist",
        f"GCC coverage: FAIL {name}:4: reviewed outcome 1 is an exception edge",
        f"GCC coverage: FAIL {name}:9: reviewed line is not executable",
    ]


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[", "not JSON"),
        (json.dumps([]), "holds only an entries array"),
        (json.dumps({"entries": {}}), "holds only an entries array"),
        (json.dumps({"entries": [], "about": "x"}), "holds only an entries array"),
        (json.dumps({"entries": [{"file": "a"}]}), "reviewed entry 0: needs exactly the keys"),
        (json.dumps({"entries": ["text"]}), "reviewed entry 0: needs exactly the keys"),
    ],
)
def test_a_malformed_reviewed_list_is_refused(tmp_path: Path, document: str, message: str) -> None:
    """Refuse a list that is not one entries array of entries with exactly the known keys.

    Parameters
    ----------
    tmp_path
        Owned directory.
    document
        The list's text.
    message
        Expected part of the refusal.
    """
    path = tmp_path / "review.json"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(CoverageError, match=message):
        load_reviewed(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"reason": " "},
        {"condition": 3},
        {"line": True},
        {"outcome": -1},
        {"lines": "4"},
        {"lines": [4.0]},
    ],
)
def test_a_reviewed_entry_with_a_wrong_field_is_refused(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    """Refuse empty texts and lines or outcomes that are not non-negative integers.

    Parameters
    ----------
    tmp_path
        Owned directory.
    changes
        One malformed field.
    """
    review = _review(tmp_path / "review.json", [_entry(tmp_path / "decide.h", **changes)])
    with pytest.raises(CoverageError, match="reviewed entry 0: needs non-empty texts"):
        load_reviewed(review)


def test_a_duplicate_entry_and_a_changed_exception_edge_are_refused(
    header: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse an outcome listed twice and reports that disagree about an exception edge.

    Parameters
    ----------
    header
        The judged header and its report.
    capsys
        Captured command output.
    """
    source, report = header
    review = _review(source.parent / "review.json", [_entry(source), _entry(source)])
    assert main(["--source", str(source), "--reviewed", str(review), str(report)]) == 2
    assert capsys.readouterr().err == (f"GCC coverage: FAIL {review}: an outcome is listed twice\n")
    changed = _load(report)
    for record in changed["files"]:
        for line in record["lines"]:
            for branch in line["branches"]:
                branch["throw"] = False
    with pytest.raises(CoverageError, match=r"decide\.h:4: branch structure differs"):
        combine([_load(report), changed], Selection.of(files=[source]))


def test_the_command_needs_a_judged_source() -> None:
    """Refuse a run that names no source directory and no source file."""
    with pytest.raises(SystemExit) as stopped:
        main(["report.json"])
    assert stopped.value.code == 2


REVIEWED_LISTS = ("runtime/coverage-review.json", "runtime/isa/plugin-coverage-review.json")
COUNT_ROW = re.compile(
    r"^\| \[`[^`]+`\]\(\.\./(?P<list>[^)]+)\) \| `(?P<source>[^`]+)` \| (?P<count>\d+) \|$"
)


def test_the_documented_counts_hold_every_reviewed_outcome() -> None:
    """The coverage document's table equals both reviewed lists, source by source.

    The committed lists are read with the gate's own loader, so a malformed edit fails here as
    well as in the native gate. Any added or removed entry changes a count, and so needs the
    public table changed in the same commit; the totals sentence follows the same counts.
    """
    document = (REPOSITORY_ROOT / "docs" / "CONTROLLER_COVERAGE.md").read_text(encoding="utf-8")
    section = document.split("## Reviewed outcome counts\n", 1)[1].split("\n## ", 1)[0]
    documented = Counter[tuple[str, str]]()
    for line in section.splitlines():
        if (row := COUNT_ROW.match(line)) is not None:
            documented[row["list"], row["source"]] += int(row["count"])
    listed = Counter(
        (name, entry.file)
        for name in REVIEWED_LISTS
        for entry in load_reviewed(REPOSITORY_ROOT / name)
    )
    assert documented == listed
    runtime, plugin = (
        sum(count for (name, _), count in listed.items() if name == list_name)
        for list_name in REVIEWED_LISTS
    )
    assert f"The runtime list holds {runtime} outcomes and the plugin list {plugin}." in section
