# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign report file tests

"""Publish campaign JSON and CSV tables that agree with the report object."""

from __future__ import annotations

import csv
import json
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness import build_campaign_report, load_campaign
from loop_timing_witness.campaign_outputs import write_campaign_report

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeRepeatCampaign


def _table(path: Path) -> list[dict[str, str]]:
    """Read one published CSV table.

    Parameters
    ----------
    path
        CSV file.

    Returns
    -------
    list[dict[str, str]]
        Rows keyed by header.
    """
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_campaign_files_match_the_report(
    make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Write every table from one report, including a refused repeat row.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Report parent directory.
    """
    path, _ = make_repeat_campaign(repeats=3)
    events = path.parent / "repeat-2" / "events.bin"
    events.write_bytes(events.read_bytes() + bytes(16))
    report = build_campaign_report(load_campaign(path))
    output = tmp_path / "campaign-report"
    write_campaign_report(output, report)
    assert sorted(item.name for item in output.iterdir()) == [
        "campaign_report.json",
        "pooled_summary.csv",
        "repeat_spread.csv",
        "repeat_summary.csv",
    ]
    assert json.loads((output / "campaign_report.json").read_bytes()) == report
    repeats = _table(output / "repeat_summary.csv")
    refused = [row for row in repeats if row["repeat_index"] == "2"]
    assert refused == [
        {
            "campaign_id": "rtl-repeat-campaign",
            "evidence_status": "simulation_only",
            "repeat_index": "2",
            "run_id": "",
            "status": "refused",
            "metric": "",
            "interval": "",
            "sample_count": "",
            "median_ticks": "",
            "p95_ticks": "",
            "p99_ticks": "",
            "p999_ticks": "",
            "maximum_ticks": "",
            "duration_ticks": "",
        }
    ]
    first = [row for row in repeats if row["repeat_index"] == "1"]
    assert sorted((row["metric"], row["interval"]) for row in first) == [
        ("jitter", "compute_time"),
        ("jitter", "loop_latency"),
        ("jitter", "scheduling_latency"),
        ("latency", "compute_time"),
        ("latency", "fault_detection"),
        ("latency", "loop_latency"),
        ("latency", "scheduling_latency"),
        ("latency", "time_to_safe_state"),
    ]
    latency = next(r for r in first if r["metric"] == "latency" and r["interval"] == "compute_time")
    assert float(latency["median_ticks"]) == 10
    assert latency["maximum_ticks"] == "5000"
    assert latency["duration_ticks"] == str(report["repeats"][0]["duration_ticks"])
    pooled = _table(output / "pooled_summary.csv")
    assert len(pooled) == 6
    jitter = next(r for r in pooled if r["metric"] == "jitter" and r["interval"] == "compute_time")
    assert jitter["repeat_count"] == "2"
    assert jitter["sample_count"] == "4"
    assert jitter["expected_pair_count"] == "4"
    assert (
        float(jitter["median_ticks"]) == report["pooled"]["jitter"]["compute_time"]["median_ticks"]
    )
    pooled_latency = next(r for r in pooled if r["metric"] == "latency")
    assert pooled_latency["expected_pair_count"] == ""
    spread = _table(output / "repeat_spread.csv")
    assert len(spread) == 2 * 3 * 5
    median = next(
        r
        for r in spread
        if (r["metric"], r["interval"], r["statistic"])
        == ("latency", "loop_latency", "median_ticks")
    )
    assert median == {
        "campaign_id": "rtl-repeat-campaign",
        "evidence_status": "simulation_only",
        "metric": "latency",
        "interval": "loop_latency",
        "statistic": "median_ticks",
        "minimum": "20.0",
        "maximum": "20.0",
        "range": "0.0",
    }


def test_existing_report_directory_is_preserved(
    make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Refuse an existing destination without changing it.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Report parent directory.
    """
    path, _ = make_repeat_campaign(repeats=1)
    report = build_campaign_report(load_campaign(path))
    output = tmp_path / "existing"
    output.mkdir()
    (output / "kept.txt").write_text("kept", encoding="utf-8")
    with pytest.raises(FileExistsError, match="report directory already exists"):
        write_campaign_report(output, report)
    assert [item.name for item in output.iterdir()] == ["kept.txt"]
    assert not [item for item in tmp_path.iterdir() if item.name.startswith(".existing.")]
