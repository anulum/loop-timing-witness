# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete native analysis coverage gate

"""Accept only complete coverage of every crate source in an llvm-cov summary."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from conftest import REPOSITORY_ROOT
from rust_coverage_gate import EXPORT, findings, main, sources

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool


def _crate(root: Path) -> Path:
    """Create a crate with a library and a binary source.

    Parameters
    ----------
    root
        Owned directory.

    Returns
    -------
    Path
        Crate directory.
    """
    crate = root / "crate"
    (crate / "src/bin").mkdir(parents=True)
    (crate / "src/lib.rs").write_text("pub fn run() {}\n", encoding="utf-8")
    (crate / "src/bin/tool.rs").write_text("fn main() {}\n", encoding="utf-8")
    (crate / "src/types.rs").write_text("// fn in a comment\npub struct Kind;\n", encoding="utf-8")
    return crate


def _measure(covered: int, count: int) -> dict[str, int]:
    """Return one llvm-cov summary measure.

    Parameters
    ----------
    covered, count
        Covered and total units.

    Returns
    -------
    dict[str, int]
        Summary measure.
    """
    return {"count": count, "covered": covered, "percent": 100}


def _summary(crate: Path, files: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """Return an export summary with covered lines and branches per named source.

    Parameters
    ----------
    crate
        Crate directory.
    files
        Source path relative to ``src`` with covered lines and branches out of ten.

    Returns
    -------
    dict[str, Any]
        Summary document.
    """
    entries = [
        {
            "filename": str(crate / "src" / name),
            "summary": {"lines": _measure(lines, 10), "branches": _measure(branches, 10)},
        }
        for name, (lines, branches) in files.items()
    ]
    totals = {"lines": _measure(20, 20), "branches": _measure(20, 20)}
    return {"type": EXPORT, "version": "3.0.1", "data": [{"files": entries, "totals": totals}]}


def test_the_crate_sources_include_the_library_and_the_command() -> None:
    """Find every maintained native source, including the installed command."""
    found = sources(REPOSITORY_ROOT / "analysis/rust")
    assert {"lib.rs", "bin/loop-timing-witness-analyze-native.rs"} <= found


def test_complete_coverage_of_every_source_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pass and report the totals when every source is completely covered.

    Parameters
    ----------
    tmp_path
        Owned crate and summary.
    capsys
        Captured command output.
    """
    crate = _crate(tmp_path)
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(_summary(crate, {"lib.rs": (10, 10), "bin/tool.rs": (10, 10)})),
        encoding="utf-8",
    )
    assert main(["--crate", str(crate), "--summary", str(summary)]) == 0
    assert capsys.readouterr().out == "native coverage: PASS lines 20/20, branches 20/20\n"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"lib.rs": (10, 10)}, ["bin/tool.rs: not measured"]),
        (
            {"lib.rs": (9, 10), "bin/tool.rs": (10, 8)},
            ["bin/tool.rs: branches 8/10", "lib.rs: lines 9/10"],
        ),
    ],
)
def test_unmeasured_and_partial_sources_fail(
    tmp_path: Path, files: dict[str, tuple[int, int]], expected: list[str]
) -> None:
    """Name each source that is missing or not completely covered.

    Parameters
    ----------
    tmp_path
        Owned crate.
    files
        Measured sources with covered lines and branches.
    expected
        Exact findings.
    """
    crate = _crate(tmp_path)
    assert findings(_summary(crate, files), crate) == expected


def test_sources_outside_the_crate_and_foreign_documents_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse a measured file outside the sources and a document of another kind.

    Parameters
    ----------
    tmp_path
        Owned crate and summary.
    capsys
        Captured command output.
    """
    crate = _crate(tmp_path)
    document = _summary(crate, {"lib.rs": (10, 10), "bin/tool.rs": (10, 10)})
    outside = str(tmp_path / "other.rs")
    document["data"][0]["files"].append({"filename": outside, "summary": {}})
    assert findings(document, crate) == [f"{outside}: measured outside the crate sources"]
    for foreign in ({"type": "other", "data": []}, {"type": EXPORT, "data": []}, {"type": EXPORT}):
        assert findings(foreign, crate) == ["Unsupported native coverage summary."]
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"type": "other"}), encoding="utf-8")
    assert main(["--crate", str(crate), "--summary", str(summary)]) == 2
    assert capsys.readouterr().err == (
        "native coverage: FAIL Unsupported native coverage summary.\n"
    )


def test_the_command_reports_through_its_exit_status(tmp_path: Path, run_tool: RunTool) -> None:
    """Run the gate as the workflow runs it and require its status and lines.

    Parameters
    ----------
    tmp_path
        Owned crate and summary.
    run_tool
        Runs one repository tool in a subprocess.
    """
    crate = _crate(tmp_path)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(_summary(crate, {"lib.rs": (10, 10)})), encoding="utf-8")
    result = run_tool("rust_coverage_gate", "--crate", str(crate), "--summary", str(summary))
    assert result.returncode == 2
    assert result.stderr == "native coverage: FAIL bin/tool.rs: not measured\n"
