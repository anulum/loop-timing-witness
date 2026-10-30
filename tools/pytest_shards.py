# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — duration-balanced pytest module shards

"""Plan, verify and time pytest module shards for the hosted coverage run.

Every discovered test module runs in exactly one shard. Measured durations
only order the assignment; they never add, drop or select modules. Without
measurements the plan is a deterministic round robin.

Commands
--------
``plan``
    Write the inventory, one module list per shard and the timing snapshot used.
``verify``
    Require exactly the planned shards, disjoint and covering the current inventory.
``record``
    Sum JUnit case durations per live module into the next timing snapshot.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import statistics
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from defusedxml import ElementTree

if TYPE_CHECKING:
    from collections.abc import Sequence

SCHEMA: Final = "loop-timing-witness.pytest-module-timings.v1"
MAXIMUM_SHARDS: Final = 16


def discover(root: Path) -> list[str]:
    """Return every test module pytest collects from ``tests``, sorted.

    Parameters
    ----------
    root
        Repository root holding the ``tests`` directory.

    Returns
    -------
    list[str]
        Repository-relative POSIX module paths.
    """
    return sorted(
        path.relative_to(root).as_posix()
        for path in (root / "tests").glob("*.py")
        if path.name.startswith("test_") or path.name.endswith("_test.py")
    )


def read_timings(path: Path | None) -> dict[str, float]:
    """Read a timing snapshot; a missing file is a cold run.

    Parameters
    ----------
    path
        Snapshot file, or ``None``.

    Returns
    -------
    dict[str, float]
        Positive finite seconds per module path.

    Raises
    ------
    ValueError
        If the snapshot is malformed or holds a nonpositive or nonfinite value.
    """
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        message = "Unsupported pytest timing snapshot."
        raise ValueError(message)
    durations = data.get("durations")
    if not isinstance(durations, dict):
        message = "Timing durations must be an object."
        raise ValueError(message)
    result: dict[str, float] = {}
    for name, seconds in durations.items():
        if type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds <= 0:
            message = "Timing entries require positive finite seconds."
            raise ValueError(message)
        result[name] = float(seconds)
    return result


def partition(modules: list[str], count: int, timings: dict[str, float]) -> list[list[str]]:
    """Assign every module once, longest measured first to the least-loaded shard.

    Parameters
    ----------
    modules
        Complete unique discovery list.
    count
        Number of nonempty shards.
    timings
        Historical durations; unmeasured modules weigh the median.

    Returns
    -------
    list[list[str]]
        Sorted module lists, one per shard.

    Raises
    ------
    ValueError
        If the count does not fit the unique module list.
    """
    if not 1 <= count <= min(len(modules), MAXIMUM_SHARDS) or len(set(modules)) != len(modules):
        message = "Shard count must fit the unique discovered module list."
        raise ValueError(message)
    if not timings:
        return [modules[index::count] for index in range(count)]
    default = statistics.median(timings.values())
    shards: list[list[str]] = [[] for _ in range(count)]
    loads = [(0.0, index) for index in range(count)]
    for name in sorted(modules, key=lambda item: (-timings.get(item, default), item)):
        load, index = heapq.heappop(loads)
        shards[index].append(name)
        heapq.heappush(loads, (load + timings.get(name, default), index))
    return [sorted(shard) for shard in shards]


def _lines(path: Path) -> list[str]:
    """Read one newline-terminated module list.

    Parameters
    ----------
    path
        Plan file.

    Returns
    -------
    list[str]
        Listed module paths.
    """
    return path.read_text(encoding="utf-8").splitlines()


def plan(root: Path, count: int, timings: Path | None, output: Path) -> None:
    """Write the inventory, shard lists and the exact timing snapshot used.

    Parameters
    ----------
    root
        Repository root.
    count
        Number of shards.
    timings
        Optional previous snapshot.
    output
        New directory for the plan.
    """
    modules = discover(root)
    durations = read_timings(timings)
    shards = partition(modules, count, durations)
    output.mkdir(parents=True)
    (output / "inventory.txt").write_text("".join(f"{name}\n" for name in modules))
    for index, shard in enumerate(shards, start=1):
        (output / f"shard-{index}.txt").write_text("".join(f"{name}\n" for name in shard))
    snapshot = {"schema": SCHEMA, "durations": durations}
    (output / "timings.json").write_text(json.dumps(snapshot, sort_keys=True) + "\n")


def verify(root: Path, directory: Path, count: int) -> None:
    """Require exactly ``count`` disjoint shards covering the current inventory.

    Parameters
    ----------
    root
        Repository root whose discovery is authoritative.
    directory
        Plan directory, possibly assembled from shard artifacts.
    count
        Expected number of shards.

    Raises
    ------
    ValueError
        If a shard is missing, extra, empty, duplicated or the union differs.
    """
    present = sorted(path.name for path in directory.glob("shard-*.txt"))
    if present != sorted(f"shard-{index}.txt" for index in range(1, count + 1)):
        message = f"Expected exactly {count} shard lists, found {present}."
        raise ValueError(message)
    listed = [_lines(directory / f"shard-{index}.txt") for index in range(1, count + 1)]
    union = [name for shard in listed for name in shard]
    if not all(listed) or len(set(union)) != len(union):
        message = "Shard lists must be nonempty and disjoint."
        raise ValueError(message)
    if sorted(union) != discover(root) or _lines(directory / "inventory.txt") != discover(root):
        message = "Shard lists differ from the discovered test inventory."
        raise ValueError(message)


def record(root: Path, reports: Path, previous: Path | None, output: Path) -> None:
    """Write the next snapshot from JUnit case durations of live modules.

    Parameters
    ----------
    root
        Repository root whose discovery defines live modules.
    reports
        Directory holding the shards' JUnit reports.
    previous
        Snapshot used by this run; unmeasured live modules keep their value.
    output
        Destination of the next snapshot.

    Raises
    ------
    ValueError
        If a duration is negative or nonfinite, or no live module was measured.
    """
    modules = {name.removesuffix(".py").replace("/", "."): name for name in discover(root)}
    durations = {
        name: seconds
        for name, seconds in read_timings(previous).items()
        if name in modules.values()
    }
    measured: dict[str, float] = {}
    for report in sorted(reports.rglob("junit-*.xml")):
        for case in ElementTree.parse(report).iter("testcase"):
            name = case.get("classname", "")
            while name and name not in modules:
                name = name.rpartition(".")[0]
            seconds = float(case.get("time", "0"))
            if not math.isfinite(seconds) or seconds < 0:
                message = "JUnit durations must be nonnegative and finite."
                raise ValueError(message)
            if name:
                measured[modules[name]] = measured.get(modules[name], 0.0) + seconds
    if not measured:
        message = "No live module durations were found in the JUnit reports."
        raise ValueError(message)
    durations.update({name: max(seconds, 0.001) for name, seconds in measured.items()})
    snapshot = {"schema": SCHEMA, "durations": durations}
    output.write_text(json.dumps(snapshot, sort_keys=True) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one scheduler command.

    Parameters
    ----------
    argv
        Command arguments; defaults to this process's arguments.

    Returns
    -------
    int
        Zero on success, two for invalid inputs.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path())
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("--count", type=int, required=True)
    planning.add_argument("--timings", type=Path)
    planning.add_argument("--output", type=Path, required=True)
    checking = commands.add_parser("verify")
    checking.add_argument("--plan", type=Path, required=True)
    checking.add_argument("--count", type=int, required=True)
    recording = commands.add_parser("record")
    recording.add_argument("--reports", type=Path, required=True)
    recording.add_argument("--previous", type=Path)
    recording.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            plan(args.root, args.count, args.timings, args.output)
        elif args.command == "verify":
            verify(args.root, args.plan, args.count)
        else:
            record(args.root, args.reports, args.previous, args.output)
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        print(f"pytest-shards: FAIL {exc}", file=sys.stderr)
        return 2
    print(f"pytest-shards: PASS {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
