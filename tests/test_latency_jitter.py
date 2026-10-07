# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — latency jitter report tests

"""Exercise jitter through hash-bound RTL captures, the public API and CLI."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness import build_report, load_run

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeRtlRun, RunTool


@pytest.mark.parametrize("profile", ["CONTROL", "COMPUTE"])
def test_jitter_reports_real_adjacent_intervals(
    profile: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Match raw pairs, Type-7 quantiles and units across every output format.

    Parameters
    ----------
    profile
        Actual RTL capture profile, with variable or constant latency.
    make_rtl_run
        Production Icarus witness capture.
    run_tool
        Public repository analyser command.
    tmp_path
        Exclusive report directory.
    """
    run, manifest = make_rtl_run(profile)
    report, intervals = build_report(load_run(run / "manifest.json"))
    jitter = report["events"]["jitter"]
    name = "compute_time" if profile == "CONTROL" else "compute_duration"
    statistics = jitter[name]
    count = manifest["cycle_count"] - 1
    assert statistics["status"] == "available"
    assert {
        key: statistics[key]
        for key in (
            "sample_count",
            "expected_pair_count",
            "missing_pair_count",
            "pair_coverage_fraction",
        )
    } == {
        "sample_count": count,
        "expected_pair_count": count,
        "missing_pair_count": 0,
        "pair_coverage_fraction": 1,
    }
    assert statistics["latency_sample_count"] == manifest["cycle_count"]
    assert statistics["duration_ticks"] == report["events"]["duration_ticks"]
    assert statistics["median_ticks"] == (2495 if profile == "CONTROL" else 0)
    assert statistics["p95_ticks"] == pytest.approx(4740.5 if profile == "CONTROL" else 0)
    assert statistics["p99_ticks"] == pytest.approx(4940.1 if profile == "CONTROL" else 0)
    assert statistics["p999_ticks"] == pytest.approx(4985.01 if profile == "CONTROL" else 0)
    assert statistics["maximum_ticks"] == (4990 if profile == "CONTROL" else 0)
    assert statistics["peak_to_peak_ticks"] == (4990 if profile == "CONTROL" else 0)
    assert "fault_detection" not in jitter
    assert "time_to_safe_state" not in jitter
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "report.json").read_bytes()) == report
    with (output / "jitter_summary.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    observed = next(row for row in rows if row["interval"] == name)
    assert observed["sample_count"] == str(count)
    assert float(observed["p99_ticks"]) == statistics["p99_ticks"]
    assert float(observed["p99_ticks"]) * int(observed["timebase_resolution_ns"]) == pytest.approx(
        statistics["p99_ticks"] * 10
    )
    assert observed["instrument_floor_ticks"] == ""
    assert observed["evidence_status"] == "simulation_only"
    assert observed["run_id"] == manifest["run_id"]
    assert observed["jitter_method"] == "absolute_cycle_to_cycle_latency_change.v1"
    with (output / "cycle_jitter.csv").open(newline="") as stream:
        pairs = list(csv.DictReader(stream))
    expected = {(int(row["cycle"]), str(row["interval"])): int(row["ticks"]) for row in intervals}
    assert len(pairs) == sum(item["sample_count"] for item in jitter.values())
    for pair in pairs:
        previous, cycle = int(pair["previous_cycle"]), int(pair["cycle"])
        interval = pair["interval"]
        assert cycle == previous + 1
        assert int(pair["previous_ticks"]) == expected[previous, interval]
        assert int(pair["ticks"]) == expected[cycle, interval]
        delta = expected[cycle, interval] - expected[previous, interval]
        assert int(pair["delta_ticks"]) == delta
        assert int(pair["absolute_delta_ticks"]) == abs(delta)
        assert pair["evidence_status"] == observed["evidence_status"]
        assert pair["jitter_method"] == observed["jitter_method"]
    svg = (output / "jitter_p99.svg").read_text()
    assert "absolute adjacent-cycle latency change" in svg
    assert "simulation_only" in svg


@pytest.mark.parametrize(
    ("variant", "expectations"),
    [
        ("gap", (2, 0, 2, "unavailable", 4990)),
        ("tail", (2, 1, 2, "partial", 0)),
        ("warmup_one", (2, 1, 1, "available", 4990)),
        ("warmup_two", (1, 0, 0, "unavailable", None)),
        ("no_reads", (0, 0, 2, "unavailable", None)),
    ],
)
def test_missing_intervals_and_warmup_never_create_pairs(
    variant: str,
    expectations: tuple[int, int, int, str, int | None],
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """Retain missing-pair counts without bridging a gap or warm-up boundary.

    Parameters
    ----------
    variant
        Controlled removal or declared warm-up of the actual capture.
    expectations
        Latency count, pair count, possible pairs, metric status and spread.
    make_rtl_run
        Real binary witness producer.
    run_tool
        Public command, checking atomic artefact integration.
    tmp_path
        Exclusive output directory.
    """
    latencies, pairs, expected, status, spread = expectations
    run, manifest = make_rtl_run()
    raw = (run / "events.bin").read_bytes()
    records = [
        struct.unpack("<BBHIQ", raw[offset : offset + 16]) for offset in range(0, len(raw), 16)
    ]
    if variant == "gap":
        records = [record for record in records if not (record[0] == 2 and record[3] == 1)]
    elif variant == "tail":
        records = [record for record in records if not (record[0] == 3 and record[3] == 2)]
    elif variant == "no_reads":
        records = [record for record in records if record[0] != 2]
    else:
        manifest["warmup_cycles"] = 1 if variant == "warmup_one" else 2
        manifest["files"]["power"] = None
        manifest["files"]["tracking"] = None
    data = b"".join(struct.pack("<BBHIQ", *record) for record in records)
    (run / "events.bin").write_bytes(data)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(data).hexdigest()
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest))
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(path), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_bytes())
    statistics = report["events"]["jitter"]["compute_time"]
    assert statistics["latency_sample_count"] == latencies
    assert statistics["sample_count"] == pairs
    assert statistics["expected_pair_count"] == expected
    assert statistics["missing_pair_count"] == expected - pairs
    assert statistics["status"] == status
    assert statistics["peak_to_peak_ticks"] == spread
    assert statistics["pair_coverage_fraction"] == (pairs / expected if expected else None)
    with (output / "cycle_jitter.csv").open(newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["interval"] == "compute_time"]
    assert len(rows) == pairs
    assert all(int(row["previous_cycle"]) >= manifest["warmup_cycles"] for row in rows)
    if not pairs:
        assert all(
            statistics[key] is None
            for key in ("median_ticks", "p95_ticks", "p99_ticks", "p999_ticks", "maximum_ticks")
        )


def test_decreasing_latency_preserves_signed_pair(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A hash-bound decreasing-latency control reports magnitude and signed delta.

    Parameters
    ----------
    make_rtl_run
        Actual COMPUTE RTL stream, retained before a timestamp mutation.
    run_tool
        Public host analyser.
    tmp_path
        Report location.
    """
    run, manifest = make_rtl_run("COMPUTE")
    raw = (run / "events.bin").read_bytes()
    records = [
        struct.unpack("<BBHIQ", raw[offset : offset + 16]) for offset in range(0, len(raw), 16)
    ]
    changed = [
        (*record[:4], 1025) if record[0] == 10 and record[3] == 1 else record for record in records
    ]
    data = b"".join(struct.pack("<BBHIQ", *record) for record in changed)
    assert data != raw
    (run / "events.bin").write_bytes(data)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(data).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_bytes())
    assert report["events"]["jitter"]["compute_duration"]["median_ticks"] == 5
    with (output / "cycle_jitter.csv").open(newline="") as stream:
        pair = next(row for row in csv.DictReader(stream) if row["interval"] == "compute_duration")
    assert pair["delta_ticks"] == "-5"
    assert pair["absolute_delta_ticks"] == "5"
