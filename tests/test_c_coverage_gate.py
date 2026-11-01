# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete C controller coverage gate

"""Combine real GCC coverage reports and accept only complete C coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from c_coverage_gate import FORMAT_VERSION, UNSUPPORTED, CoverageError, combine, findings, main

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
    alone = findings(combine([_load(negative)], tree / "sources"), tree / "sources")
    assert len(alone) == 2
    assert alone[0].startswith("choose.c: lines 3/4, unexecuted 3")
    assert alone[1].startswith("choose.c: branches 1/2, untaken on lines 2")
    assert main(["--sources", str(tree / "sources"), str(negative), str(positive)]) == 0
    assert capsys.readouterr().out == "C coverage: PASS lines 4/4, branches 2/2\n"


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
    combined = combine([report, driver_report], tree / "sources")
    assert set(combined) == {"choose.c"}
    (tree / "sources/added.c").write_text("int added(void) { return 0; }\n", encoding="utf-8")
    assert findings(combined, tree / "sources")[0] == "added.c: not measured"


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
    sources = tree / "sources"
    for document in ({"format_version": "0", "files": []}, {"format_version": FORMAT_VERSION}):
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
    assert main(["--sources", str(sources), str(path)]) == 2
    assert capsys.readouterr().err == f"C coverage: FAIL {UNSUPPORTED}\n"


def test_long_uncovered_ranges_are_shortened(tree: Path) -> None:
    """List at most ten unexecuted lines and mark the rest.

    Parameters
    ----------
    tree
        Owned source tree.
    """
    lines = [{"line_number": number, "count": 0, "branches": []} for number in range(1, 13)]
    report = {
        "format_version": FORMAT_VERSION,
        "current_working_directory": str(tree),
        "files": [{"file": str(tree / "sources/choose.c"), "lines": lines}],
    }
    assert findings(combine([report], tree / "sources"), tree / "sources") == [
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
    assert result.stderr.splitlines()[0] == "C coverage: FAIL choose.c: lines 3/4, unexecuted 3"
