# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — duration-balanced pytest module shards

"""Plan, verify and time shards on real module trees and JUnit reports."""

from __future__ import annotations

import json
import math
import shutil
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT
from pytest_shards import SCHEMA, discover, main, partition, read_timings

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool


def _tree(root: Path, names: list[str]) -> Path:
    """Create a repository root whose ``tests`` hold the named files.

    Parameters
    ----------
    root
        Owned directory.
    names
        File names inside ``tests``.

    Returns
    -------
    Path
        The repository root.
    """
    (root / "tests").mkdir(parents=True)
    for name in names:
        (root / "tests" / name).write_text("")
    return root


def _snapshot(path: Path, durations: object) -> Path:
    """Write one timing snapshot.

    Parameters
    ----------
    path
        Destination.
    durations
        Value stored under ``durations``.

    Returns
    -------
    Path
        The snapshot path.
    """
    path.write_text(json.dumps({"schema": SCHEMA, "durations": durations}))
    return path


def _junit(path: Path, cases: list[tuple[str, str]]) -> None:
    """Write one JUnit report with the given class names and times.

    Parameters
    ----------
    path
        Destination.
    cases
        Class name and time attribute of each case.
    """
    body = "".join(f'<testcase classname="{name}" name="t" time="{time}"/>' for name, time in cases)
    path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")


def test_discovery_matches_pytest_collection_rules(tmp_path: Path) -> None:
    """Collect ``test_*.py`` and ``*_test.py`` only, sorted."""
    root = _tree(tmp_path, ["test_b.py", "a_test.py", "helper.py", "conftest.py", "test_a.txt"])
    assert discover(root) == ["tests/a_test.py", "tests/test_b.py"]
    assert len(discover(REPOSITORY_ROOT)) > 100


def test_cold_plan_is_round_robin_and_measured_plan_balances() -> None:
    """Round robin without timings; longest first to the least-loaded shard otherwise."""
    modules = [f"tests/test_{index}.py" for index in range(5)]
    assert partition(modules, 2, {}) == [modules[0::2], modules[1::2]]
    timings = {modules[0]: 10.0, modules[1]: 6.0, modules[2]: 5.0}
    shards = partition(modules, 2, timings)
    assert shards == [[modules[0], modules[4]], [modules[1], modules[2], modules[3]]]
    assert sorted(name for shard in shards for name in shard) == modules


@pytest.mark.parametrize("count", [0, 3, 17])
def test_partition_refuses_counts_that_do_not_fit(count: int) -> None:
    """Refuse zero, more shards than modules and more than the maximum."""
    modules = [f"tests/test_{index}.py" for index in range(2 if count == 3 else 20)]
    with pytest.raises(ValueError, match="Shard count"):
        partition(modules, count, {})


def test_partition_refuses_duplicate_modules() -> None:
    """A duplicated module could run twice."""
    with pytest.raises(ValueError, match="Shard count"):
        partition(["tests/test_a.py", "tests/test_a.py"], 1, {})


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"schema": "other", "durations": {}},
        {"schema": SCHEMA, "durations": []},
        {"schema": SCHEMA, "durations": {"tests/test_a.py": 0}},
        {"schema": SCHEMA, "durations": {"tests/test_a.py": True}},
        {"schema": SCHEMA, "durations": {"tests/test_a.py": "1"}},
        {"schema": SCHEMA, "durations": {"tests/test_a.py": math.inf}},
    ],
)
def test_malformed_snapshots_refuse(tmp_path: Path, document: object) -> None:
    """Refuse every malformed, nonpositive, boolean, textual or infinite weight."""
    path = tmp_path / "timings.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match=r"pytest timing snapshot|Timing"):
        read_timings(path)


def test_missing_snapshot_is_a_cold_run(tmp_path: Path) -> None:
    """An absent file and no file both mean no measurements."""
    assert read_timings(None) == {}
    assert read_timings(tmp_path / "absent.json") == {}
    assert read_timings(_snapshot(tmp_path / "t.json", {"tests/test_a.py": 2})) == {
        "tests/test_a.py": 2.0
    }


def test_plan_verify_and_record_round_trip(tmp_path: Path, run_tool: RunTool) -> None:
    """Plan through the CLI, verify the union and record the next snapshot."""
    root = _tree(tmp_path / "repo", ["test_a.py", "test_b.py", "test_c.py"])
    previous = _snapshot(tmp_path / "previous.json", {"tests/test_a.py": 5, "tests/gone.py": 1})
    result = run_tool(
        "pytest_shards",
        "--root",
        str(root),
        "plan",
        "--count",
        "2",
        "--timings",
        str(previous),
        "--output",
        str(tmp_path / "plan"),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "pytest-shards: PASS plan\n"
    plan = tmp_path / "plan"
    assert (plan / "shard-1.txt").read_text() == "tests/test_a.py\n"
    assert (plan / "shard-2.txt").read_text() == "tests/test_b.py\ntests/test_c.py\n"
    used = json.loads((plan / "timings.json").read_text())
    assert used == {"schema": SCHEMA, "durations": {"tests/gone.py": 1.0, "tests/test_a.py": 5.0}}
    assert main(["--root", str(root), "verify", "--plan", str(plan), "--count", "2"]) == 0
    reports = tmp_path / "reports"
    reports.mkdir()
    _junit(
        reports / "junit-1.xml",
        [("tests.test_b", "1.5"), ("tests.test_b.TestCase", "0.5"), ("other.module", "9")],
    )
    _junit(reports / "junit-2.xml", [("tests.test_c", "0")])
    output = tmp_path / "next.json"
    arguments = ["--root", str(root), "record", "--reports", str(reports)]
    assert main([*arguments, "--previous", str(previous), "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == {
        "schema": SCHEMA,
        "durations": {"tests/test_a.py": 5.0, "tests/test_b.py": 2.0, "tests/test_c.py": 0.001},
    }


@pytest.mark.parametrize("damage", ["missing", "extra", "empty", "duplicate", "inventory", "new"])
def test_verify_refuses_incomplete_or_inconsistent_shards(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], damage: str
) -> None:
    """Refuse a missing, extra, empty or duplicated shard and any inventory drift."""
    root = _tree(tmp_path / "repo", ["test_a.py", "test_b.py"])
    plan = tmp_path / "plan"
    assert main(["--root", str(root), "plan", "--count", "2", "--output", str(plan)]) == 0
    if damage == "missing":
        (plan / "shard-2.txt").unlink()
    elif damage == "extra":
        shutil.copyfile(plan / "shard-2.txt", plan / "shard-3.txt")
    elif damage == "empty":
        (plan / "shard-2.txt").write_text("")
    elif damage == "duplicate":
        (plan / "shard-2.txt").write_text("tests/test_a.py\n")
    elif damage == "inventory":
        (plan / "inventory.txt").write_text("tests/test_a.py\n")
    else:
        (root / "tests" / "test_new.py").write_text("")
    capsys.readouterr()
    assert main(["--root", str(root), "verify", "--plan", str(plan), "--count", "2"]) == 2
    assert capsys.readouterr().err.startswith("pytest-shards: FAIL ")


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        ([("tests.test_a", "-1")], "nonnegative and finite"),
        ([("tests.test_a", "nan")], "nonnegative and finite"),
        ([("other", "1")], "No live module"),
    ],
)
def test_record_refuses_invalid_or_absent_measurements(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], cases: list[tuple[str, str]], message: str
) -> None:
    """Refuse negative or nonfinite durations and reports without live modules."""
    root = _tree(tmp_path / "repo", ["test_a.py"])
    reports = tmp_path / "reports"
    reports.mkdir()
    _junit(reports / "junit-1.xml", cases)
    arguments = ["--root", str(root), "record", "--reports", str(reports)]
    assert main([*arguments, "--output", str(tmp_path / "next.json")]) == 2
    assert message in capsys.readouterr().err


def test_record_refuses_malformed_xml_and_plan_refuses_existing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse an unparsable report and never overwrite an existing plan."""
    root = _tree(tmp_path / "repo", ["test_a.py"])
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "junit-1.xml").write_text("<testsuites>")
    arguments = ["--root", str(root), "record", "--reports", str(reports)]
    assert main([*arguments, "--output", str(tmp_path / "next.json")]) == 2
    plan = tmp_path / "plan"
    plan.mkdir()
    assert main(["--root", str(root), "plan", "--count", "1", "--output", str(plan)]) == 2
    assert capsys.readouterr().err.count("pytest-shards: FAIL ") == 2
