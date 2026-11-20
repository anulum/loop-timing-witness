# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tail quantile intervals of a published run report

"""Check the tail-interval command on a real analysed run and on report directories it refuses."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from math import ceil, floor
from typing import TYPE_CHECKING, Any

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled
from loop_timing_witness.run_analysis import distribution
from loop_timing_witness.tail_intervals import main, tail_intervals
from loop_timing_witness.tail_statistics import (
    QUANTILES,
    RESAMPLES,
    SEED,
    SplitMix64,
    block_length,
    tail_quantiles,
    type7,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]
    RunTool = Callable[..., subprocess.CompletedProcess[str]]


def _naive(values: list[int]) -> dict[str, tuple[float, float]]:
    """Bootstrap the reportable quantiles with a full sort of every resample.

    Parameters
    ----------
    values
        Samples in cycle order.

    Returns
    -------
    dict[str, tuple[float, float]]
        Interval bounds per reportable quantile.
    """
    count = len(values)
    length = block_length(count)
    generator = SplitMix64(SEED)
    blocks = ceil(count / length)
    estimates: dict[str, list[float]] = {name: [] for name, _ in QUANTILES}
    for _ in range(RESAMPLES):
        resample: list[int] = []
        for _ in range(blocks):
            start = generator.next() % (count - length + 1)
            resample.extend(values[start : start + length])
        resample = sorted(resample[:count])
        for name, thousandths in QUANTILES:
            estimates[name].append(type7(resample, thousandths / 1000))
    return {
        name: (type7(sorted(estimates[name]), 0.025), type7(sorted(estimates[name]), 0.975))
        for name, thousandths in QUANTILES
        if count * (1000 - thousandths) >= 10000
    }


@pytest.mark.parametrize(
    "values",
    [
        [100 + (index * 37) % 101 for index in range(1000)],
        [7] * 990 + [9] * 10,
        [5] * 1200,
        [1000 + (400 if index % 300 < 20 else 0) for index in range(600)],
    ],
    ids=["spread", "ties", "constant", "bursts"],
)
def test_tail_set_resampling_equals_full_sorts(values: list[int]) -> None:
    """The tail-set method, and its full-sort fallback for heavy ties, give the full-sort bounds.

    Parameters
    ----------
    values
        Samples in cycle order.
    """
    quantiles = tail_quantiles(values)["quantiles"]
    expected = _naive(values)
    assert expected
    for name, (lower, upper) in expected.items():
        assert (quantiles[name]["lower"], quantiles[name]["upper"]) == (lower, upper)


def _report_directory(directory: Path, samples: dict[str, list[int]]) -> Path:
    """Write the two files of a report directory from interval samples.

    Parameters
    ----------
    directory
        New report directory.
    samples
        Tick samples per interval, in cycle order.

    Returns
    -------
    Path
        The directory.
    """
    directory.mkdir()
    intervals = {name: distribution(values) for name, values in samples.items()}
    intervals["fault_detection"] = distribution([])
    report = {
        "run_id": "run-1",
        "evidence_status": "simulation_only",
        "events": {"intervals": intervals},
    }
    (directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
    rows = "".join(
        f"run-1,simulation_only,{cycle},{name},{value}\n"
        for name, values in samples.items()
        for cycle, value in enumerate(values)
    )
    (directory / "cycle_intervals.csv").write_text(
        "run_id,evidence_status,cycle,interval,ticks\n" + rows, encoding="utf-8"
    )
    return directory


def test_report_intervals_are_bounded_and_bound_to_both_files(tmp_path: Path) -> None:
    """Every periodic interval gets its tail intervals, and the result names both files.

    Parameters
    ----------
    tmp_path
        Report directory.
    """
    samples = {
        "loop_latency": [100 + (index * 37) % 101 for index in range(1000)],
        "compute_time": [5, 6, 7],
    }
    directory = _report_directory(tmp_path / "report", samples)
    result = tail_intervals(directory)
    assert result["schema"] == "loop-timing-witness.tail-intervals.v1"
    assert (
        result["report_sha256"]
        == hashlib.sha256((directory / "report.json").read_bytes()).hexdigest()
    )
    assert (
        result["cycle_intervals_sha256"]
        == hashlib.sha256((directory / "cycle_intervals.csv").read_bytes()).hexdigest()
    )
    assert set(result["intervals"]) == {"loop_latency", "compute_time"}
    assert result["intervals"]["loop_latency"] == tail_quantiles(samples["loop_latency"])
    assert result["intervals"]["compute_time"]["resamples"] == 0


def test_real_analysed_run(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command accepts the report directory that the run analysis published.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    run_tool
        Repository tool runner.
    tmp_path
        Report directory.
    capsys
        Captured standard output.
    """
    run, _ = make_rtl_run()
    output = tmp_path / "reports"
    analysis = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert analysis.returncode == 0, analysis.stderr
    assert main([str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert result["run_id"] == report["run_id"]
    assert result["intervals"]
    for name, entry in result["intervals"].items():
        assert entry["sample_count"] == report["events"]["intervals"][name]["sample_count"]


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("header", "header differs"),
        ("foreign row", "does not belong to the report"),
        ("evidence", "does not belong to the report"),
        ("ticks", "does not belong to the report"),
        ("count", "samples of loop_latency differ from the report"),
        ("estimate", "samples of loop_latency differ from the report"),
        ("unknown interval", "samples of other differ from the report"),
        ("no intervals", "report has no interval distributions"),
        ("missing table", "No such file"),
        ("bytes", "codec can't decode"),
        ("quote", "unexpected end of data"),
    ],
)
def test_refused_report_directories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str, error: str
) -> None:
    """A table or report that is not the report's own is refused with status 2.

    Parameters
    ----------
    tmp_path
        Report directory.
    capsys
        Captured standard error.
    change
        Damage applied to the report directory.
    error
        Expected refusal text.
    """
    directory = _report_directory(tmp_path / "report", {"loop_latency": [10, 11, 12, 13]})
    table = directory / "cycle_intervals.csv"
    report = directory / "report.json"
    text = table.read_text(encoding="utf-8")
    edits: dict[str, Callable[[], object]] = {
        "header": lambda: table.write_text(text.replace("ticks", "tick", 1), encoding="utf-8"),
        "foreign row": lambda: table.write_text(
            text + "run-2,simulation_only,9,loop_latency,1\n", encoding="utf-8"
        ),
        "evidence": lambda: table.write_text(
            text.replace("simulation_only", "board", 2), encoding="utf-8"
        ),
        "ticks": lambda: table.write_text(
            text + "run-1,simulation_only,9,loop_latency,-1\n", encoding="utf-8"
        ),
        "count": lambda: table.write_text(
            text + "run-1,simulation_only,9,loop_latency,12\n", encoding="utf-8"
        ),
        "estimate": lambda: table.write_text(text.replace(",13\n", ",14\n"), encoding="utf-8"),
        "unknown interval": lambda: table.write_text(
            text + "run-1,simulation_only,0,other,1\n", encoding="utf-8"
        ),
        "no intervals": lambda: report.write_text('{"run_id": "run-1"}', encoding="utf-8"),
        "missing table": table.unlink,
        "bytes": lambda: table.write_bytes(b"\xff\xfe"),
        "quote": lambda: table.write_text(text + 'run-1,"simulation_only\n', encoding="utf-8"),
    }
    edits[change]()
    assert main([str(directory)]) == 2
    assert error in capsys.readouterr().err


def test_module_command_and_usage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The module command prints the result; the command takes exactly one report directory.

    Parameters
    ----------
    tmp_path
        Report directory.
    capsys
        Captured standard error.
    """
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err
    directory = _report_directory(tmp_path / "report", {"loop_latency": [10, 11, 12]})
    result = subprocess.run(
        [sys.executable, "-m", "loop_timing_witness.tail_intervals", str(directory)],
        cwd=REPOSITORY_ROOT,
        env={**os.environ},
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["method"] == "moving_block_bootstrap_percentile"


def test_quantile_positions_follow_type7() -> None:
    """The interpolation positions of the three quantiles match the distribution's."""
    values = list(range(37))
    for name, thousandths in QUANTILES:
        position = (len(values) - 1) * (thousandths / 1000)
        assert type7(values, thousandths / 1000) == values[floor(position)] + (
            values[ceil(position)] - values[floor(position)]
        ) * (position - floor(position))
        assert tail_quantiles(values)["quantiles"][name]["estimate"] == distribution(values)[name]
