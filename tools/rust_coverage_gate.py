# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete native analysis line and branch coverage

"""Require every line and branch of every native analysis source to be covered.

The summary is ``llvm-cov export -summary-only`` of the profiles merged from
every instrumented native test and every parity run against the instrumented
registry consumer. Every Rust file under the crate's ``src`` must appear in it
with all lines and branches covered. ``llvm-cov`` lists no file without
executable code, so a source may be absent only when it declares no function;
any other absent source fails, so a new file cannot pass unmeasured. A measured
file outside ``src`` fails too.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

EXPORT: Final = "llvm.coverage.json.export"
_FUNCTION: Final = re.compile(r"\bfn\b")


def sources(crate: Path) -> set[str]:
    """Return every Rust source of the crate, relative to its ``src``.

    Parameters
    ----------
    crate
        Crate directory holding ``src``.

    Returns
    -------
    set[str]
        POSIX paths relative to ``src``.
    """
    root = crate / "src"
    return {path.relative_to(root).as_posix() for path in root.rglob("*.rs")}


def declares_functions(path: Path) -> bool:
    """Tell whether a Rust source declares a function outside line comments.

    Parameters
    ----------
    path
        Rust source file.

    Returns
    -------
    bool
        Whether any non-comment line holds the ``fn`` keyword.
    """
    return any(
        _FUNCTION.search(line) and not line.lstrip().startswith("//")
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def _covered(summary: dict[str, Any], kind: str) -> tuple[int, int]:
    """Return the covered and total count of one summary measure.

    Parameters
    ----------
    summary
        One file's or the total summary.
    kind
        ``lines`` or ``branches``.

    Returns
    -------
    tuple[int, int]
        Covered and total counts.
    """
    measure = summary[kind]
    return int(measure["covered"]), int(measure["count"])


def findings(summary: dict[str, Any], crate: Path) -> list[str]:
    """Return every reason the summary does not show complete coverage of the crate.

    Parameters
    ----------
    summary
        Decoded ``llvm-cov export -summary-only`` document.
    crate
        Crate directory whose ``src`` must be completely covered.

    Returns
    -------
    list[str]
        Unsupported summary, unmeasured, outside or incompletely covered files;
        empty when coverage is complete.
    """
    data = summary.get("data")
    if summary.get("type") != EXPORT or not isinstance(data, list) or len(data) != 1:
        return ["Unsupported native coverage summary."]
    root = (crate / "src").resolve()
    measured: dict[str, dict[str, Any]] = {}
    result = []
    for item in data[0]["files"]:
        path = Path(item["filename"]).resolve()
        if not path.is_relative_to(root):
            result.append(f"{item['filename']}: measured outside the crate sources")
            continue
        measured[path.relative_to(root).as_posix()] = item["summary"]
    result.extend(
        f"{name}: not measured"
        for name in sorted(sources(crate) - set(measured))
        if declares_functions(root / name)
    )
    for name, file_summary in sorted(measured.items()):
        for kind in ("lines", "branches"):
            covered, count = _covered(file_summary, kind)
            if covered != count:
                result.append(f"{name}: {kind} {covered}/{count}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """Check one coverage summary against the crate sources.

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
    parser.add_argument("--crate", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    failures = findings(summary, args.crate)
    if failures:
        for failure in failures:
            print(f"native coverage: FAIL {failure}", file=sys.stderr)
        return 2
    totals = summary["data"][0]["totals"]
    lines = "{}/{}".format(*_covered(totals, "lines"))
    branches = "{}/{}".format(*_covered(totals, "branches"))
    print(f"native coverage: PASS lines {lines}, branches {branches}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
