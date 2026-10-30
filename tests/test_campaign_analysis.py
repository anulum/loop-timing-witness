# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign statistics tests

"""Pool real RTL repeats, state their spread and keep failed repeats visible."""

from __future__ import annotations

import hashlib
import json
import struct
from typing import TYPE_CHECKING, Any

import pytest

from conftest import write_bound_json
from loop_timing_witness import build_campaign_report, build_report, load_campaign, load_run
from loop_timing_witness.latency_jitter import jitter_pairs
from loop_timing_witness.run_analysis import distribution

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from conftest import MakeRepeatCampaign

RECORD = struct.Struct("<BBHIQ")
SAMPLE_READ = 2
ACT_WRITE = 3
CONTROL_INTERVALS = ["scheduling_latency", "compute_time", "loop_latency"]


def _rewrite_events(
    path: Path, document: dict[str, Any], index: int, change: Callable[[bytes], bytes]
) -> None:
    """Replace one repeat's captured events and bind the new bytes.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    index
        One-based repeat index.
    change
        Transformation of the complete event file.
    """
    entry = document["repeats"][index - 1]
    run_path = path.parent / entry["run_manifest"]["path"]
    events = run_path.parent / "events.bin"
    events.write_bytes(change(events.read_bytes()))
    manifest = json.loads(run_path.read_bytes())
    manifest["files"]["events"]["sha256"] = hashlib.sha256(events.read_bytes()).hexdigest()
    entry["run_manifest"] = write_bound_json(run_path, manifest)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _rebind_repeat(
    path: Path, document: dict[str, Any], index: int, change: dict[str, Any]
) -> None:
    """Change top-level fields of one repeat's run manifest and bind its digest.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    index
        One-based repeat index.
    change
        Run manifest fields to replace.
    """
    entry = document["repeats"][index - 1]
    run_path = path.parent / entry["run_manifest"]["path"]
    entry["run_manifest"] = write_bound_json(
        run_path, {**json.loads(run_path.read_bytes()), **change}
    )
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _delay_from_first_write(events: bytes, ticks: int) -> bytes:
    """Delay the first actuator write and every later record by a fixed amount.

    Parameters
    ----------
    events
        Complete little-endian 16-byte witness records.
    ticks
        Added timebase ticks.

    Returns
    -------
    bytes
        Records with unchanged order; only the cycle-0 compute and loop
        latencies change.
    """
    records = [list(RECORD.unpack_from(events, offset)) for offset in range(0, len(events), 16)]
    start = next(i for i, record in enumerate(records) if record[0] == ACT_WRITE)
    for record in records[start:]:
        record[4] += ticks
    return b"".join(RECORD.pack(*record) for record in records)


def _without_cycle_one_sample_read(events: bytes) -> bytes:
    """Remove the cycle-1 sample-read record.

    Parameters
    ----------
    events
        Complete witness records.

    Returns
    -------
    bytes
        Records without that single event.
    """
    return b"".join(
        events[offset : offset + 16]
        for offset in range(0, len(events), 16)
        if RECORD.unpack_from(events, offset)[0:4:3] != (SAMPLE_READ, 1)
    )


def _run_reports(path: Path, document: dict[str, Any], indexes: list[int]) -> list[Any]:
    """Analyse selected repeats directly through the public run interface.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document.
    indexes
        One-based repeat indexes.

    Returns
    -------
    list[Any]
        Run report and interval rows for each selected repeat.
    """
    return [
        build_report(load_run(path.parent / document["repeats"][i - 1]["run_manifest"]["path"]))
        for i in indexes
    ]


def test_identical_repeats_pool_raw_samples(make_repeat_campaign: MakeRepeatCampaign) -> None:
    """Concatenate raw latencies and within-run jitter pairs of five repeats.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign()
    report = build_campaign_report(load_campaign(path))
    runs = _run_reports(path, document, [1, 2, 3, 4, 5])
    assert report["schema"] == "loop-timing-witness.repeat-campaign-report.v1"
    assert report["campaign_id"] == "rtl-repeat-campaign"
    assert report["evidence_status"] == "simulation_only"
    assert report["timebase_resolution_ns"] == 10
    assert [entry["status"] for entry in report["repeats"]] == ["valid"] * 5
    assert [entry["run_id"] for entry in report["repeats"]] == [
        f"rtl-repeat-{index}" for index in range(1, 6)
    ]
    for entry, (run, _) in zip(report["repeats"], runs, strict=True):
        assert entry["intervals"] == run["events"]["intervals"]
        assert entry["jitter"] == run["events"]["jitter"]
        assert entry["control"] == run["events"]["control"]
        assert entry["analysed_cycles"] == 3
    pooled = report["pooled"]
    assert pooled["repeat_count"] == 5
    assert pooled["cycle_count"] == 15
    assert pooled["duration_ticks"] == 5 * runs[0][0]["events"]["duration_ticks"]
    compute = pooled["intervals"]["compute_time"]
    assert {key: compute[key] for key in ("sample_count", "median_ticks", "maximum_ticks")} == {
        "sample_count": 15,
        "median_ticks": 10,
        "maximum_ticks": 5000,
    }
    assert compute["p95_ticks"] == 5000
    jitter = pooled["jitter"]["compute_time"]
    assert jitter["sample_count"] == 10
    assert jitter["expected_pair_count"] == 10
    assert jitter["missing_pair_count"] == 0
    assert jitter["pair_coverage_fraction"] == 1
    assert jitter["status"] == "available"
    assert jitter["median_ticks"] == 2495
    assert jitter["p95_ticks"] == 4990
    for name in CONTROL_INTERVALS:
        latencies = [
            int(row["ticks"]) for _, rows in runs for row in rows if row["interval"] == name
        ]
        changes = [
            int(pair["absolute_delta_ticks"])
            for _, rows in runs
            for pair in jitter_pairs(rows)
            if pair["interval"] == name
        ]
        assert pooled["intervals"][name] == {
            **distribution(latencies),
            "duration_ticks": pooled["duration_ticks"],
        }
        assert {key: pooled["jitter"][name][key] for key in distribution(changes)} == distribution(
            changes
        )
        for statistic in report["spread"]["intervals"][name].values():
            assert statistic["range"] == 0
    control = pooled["control"]
    assert (
        control["observed_deadlines"] == 5 * runs[0][0]["events"]["control"]["observed_deadlines"]
    )
    assert control["deadline_misses"] == 5 * runs[0][0]["events"]["control"]["deadline_misses"]
    assert report["status"] == "incomplete"
    assert report["plan"]["planned_repeats"] == 5
    assert report["plan"]["nonconformities"] == [
        "3 analysed cycles per repeat; the run plan requires 1000000"
    ]
    assert "RTL simulation repeats are not board measurements." in report["limits"]
    assert report["configuration"]["load_case"] == "idle"


def test_campaign_meeting_its_run_plan_is_complete(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Mark a campaign complete only when every plan condition holds.

    Parameters
    ----------
    make_repeat_campaign
        Campaign whose domain copy plans five three-cycle repeats.
    """
    path, _ = make_repeat_campaign(run_plan={"cycles_per_repeat": 3, "repeats": 5})
    report = build_campaign_report(load_campaign(path))
    assert report["status"] == "complete"
    assert report["plan"] == {
        "planned_repeats": 5,
        "planned_cycles_per_repeat": 3,
        "declared_repeats": 5,
        "valid_repeats": 5,
        "invalid_repeats": 0,
        "refused_repeats": 0,
        "conforms": True,
        "nonconformities": [],
    }


def test_spread_states_the_range_of_each_repeat_statistic(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Report the range of per-repeat medians when one repeat differs.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign()
    _rewrite_events(path, document, 2, lambda events: _delay_from_first_write(events, 3))
    report = build_campaign_report(load_campaign(path))
    assert report["repeats"][1]["status"] == "valid"
    assert report["repeats"][1]["intervals"]["compute_time"]["median_ticks"] == 13
    assert report["spread"]["intervals"]["compute_time"]["median_ticks"] == {
        "minimum": 10,
        "maximum": 13,
        "range": 3,
    }
    assert report["spread"]["intervals"]["scheduling_latency"]["median_ticks"]["range"] == 0
    assert report["spread"]["jitter"]["compute_time"]["median_ticks"] == {
        "minimum": 2495,
        "maximum": 2496.5,
        "range": 1.5,
    }
    runs = _run_reports(path, document, [1, 2, 3, 4, 5])
    latencies = [
        int(row["ticks"]) for _, rows in runs for row in rows if row["interval"] == "compute_time"
    ]
    assert report["pooled"]["intervals"]["compute_time"]["sample_count"] == 15
    assert (
        report["pooled"]["intervals"]["compute_time"]["median_ticks"]
        == (distribution(latencies)["median_ticks"])
    )


def test_invalid_and_refused_repeats_stay_visible_without_samples(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """List an overflowed, an unloadable and an unanalysable repeat.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign()
    run = json.loads((path.parent / "repeat-4" / "manifest.json").read_bytes())
    _rebind_repeat(
        path, document, 4, {"instrument": {**run["instrument"], "fifo_overflow_count": 1}}
    )
    _rewrite_events(path, document, 3, lambda events: events[:-1])
    events = path.parent / "repeat-5" / "events.bin"
    events.write_bytes(events.read_bytes() + bytes(16))
    report = build_campaign_report(load_campaign(path))
    statuses = [entry["status"] for entry in report["repeats"]]
    assert statuses == ["valid", "valid", "refused", "invalid", "refused"]
    assert report["repeats"][3]["invalid_reasons"] == ["event FIFO overflow"]
    assert report["repeats"][2]["run_id"] == "rtl-repeat-3"
    assert report["repeats"][2]["refusal"]
    assert report["repeats"][2]["intervals"] is None
    assert report["repeats"][4]["run_id"] is None
    assert report["repeats"][4]["refusal"] == "input SHA-256 mismatch: events.bin"
    assert report["pooled"]["repeat_count"] == 2
    assert report["pooled"]["run_ids"] == ["rtl-repeat-1", "rtl-repeat-2"]
    assert report["pooled"]["intervals"]["compute_time"]["sample_count"] == 6
    assert report["plan"]["valid_repeats"] == 2
    assert report["plan"]["invalid_repeats"] == 1
    assert report["plan"]["refused_repeats"] == 2
    assert report["plan"]["nonconformities"] == [
        "repeat 3 is refused",
        "repeat 4 is invalid",
        "repeat 5 is refused",
        "3 analysed cycles per repeat; the run plan requires 1000000",
    ]


def test_missing_reboot_and_repeat_count_are_nonconformities(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Report a short campaign and an undeclared reboot.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of three copied captures under a five-repeat plan.
    """
    path, document = make_repeat_campaign(
        repeats=3, run_plan={"cycles_per_repeat": 3, "repeats": 5}
    )
    document["repeats"][1]["rebooted_before_run"] = False
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    report = build_campaign_report(load_campaign(path))
    assert report["status"] == "incomplete"
    assert report["plan"]["nonconformities"] == [
        "3 repeats declared; the run plan requires 5",
        "repeat 2 did not reboot before its run",
    ]
    assert report["pooled"]["repeat_count"] == 3


def test_gapped_cycles_give_partial_pooled_jitter(make_repeat_campaign: MakeRepeatCampaign) -> None:
    """Never bridge a missing cycle inside a repeat or across repeats.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign(repeats=2)
    _rewrite_events(path, document, 1, _without_cycle_one_sample_read)
    report = build_campaign_report(load_campaign(path))
    assert [entry["status"] for entry in report["repeats"]] == ["valid", "valid"]
    compute = report["pooled"]["jitter"]["compute_time"]
    assert compute["status"] == "partial"
    assert compute["expected_pair_count"] == 4
    assert compute["sample_count"] == 2
    assert compute["missing_pair_count"] == 2
    assert compute["pair_coverage_fraction"] == 0.5
    assert report["pooled"]["jitter"]["loop_latency"]["status"] == "available"


def test_compute_profile_has_no_control_statistics(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Pool COMPUTE repeats without inventing deadline counts.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real COMPUTE captures.
    """
    path, _ = make_repeat_campaign(repeats=2, profile="COMPUTE")
    report = build_campaign_report(load_campaign(path))
    assert [entry["status"] for entry in report["repeats"]] == ["valid", "valid"]
    assert report["pooled"]["control"] is None
    assert report["pooled"]["jitter"]["compute_duration"]["sample_count"] == 2
    assert report["configuration"]["profile"] == "COMPUTE"


@pytest.mark.parametrize("stage", ["load", "analysis"])
def test_campaign_without_an_analysed_repeat(
    make_repeat_campaign: MakeRepeatCampaign, stage: str
) -> None:
    """Report every repeat refused, with no pooled sample and no spread.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    stage
        Whether the runs fail to load or load but cannot be analysed.
    """
    path, document = make_repeat_campaign(repeats=2)
    for index in (1, 2):
        if stage == "load":
            events = path.parent / f"repeat-{index}" / "events.bin"
            events.write_bytes(events.read_bytes() + bytes(16))
        else:
            _rewrite_events(path, document, index, lambda events: events[:-1])
    report = build_campaign_report(load_campaign(path))
    assert [entry["status"] for entry in report["repeats"]] == ["refused", "refused"]
    assert report["pooled"]["repeat_count"] == 0
    assert report["pooled"]["intervals"] == {}
    assert report["pooled"]["jitter"] == {}
    assert report["pooled"]["control"] is None
    assert report["spread"] == {"intervals": {}, "jitter": {}}
    if stage == "load":
        assert report["evidence_status"] == "unavailable"
        assert report["configuration"] is None
        assert report["timebase_resolution_ns"] is None
        assert report["plan"]["planned_repeats"] is None
        assert report["plan"]["nonconformities"][0] == (
            "no repeat could be loaded; the run plan is unavailable"
        )
    else:
        assert report["evidence_status"] == "simulation_only"
        assert report["plan"]["planned_repeats"] == 5


def test_spread_is_null_without_valid_repeats(make_repeat_campaign: MakeRepeatCampaign) -> None:
    """State no spread when every analysed repeat is invalid.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign(repeats=1)
    run = json.loads((path.parent / "repeat-1" / "manifest.json").read_bytes())
    _rebind_repeat(
        path, document, 1, {"instrument": {**run["instrument"], "fifo_overflow_count": 2}}
    )
    report = build_campaign_report(load_campaign(path))
    assert report["repeats"][0]["status"] == "invalid"
    assert report["spread"]["intervals"]["compute_time"]["median_ticks"] == {
        "minimum": None,
        "maximum": None,
        "range": None,
    }
    assert report["pooled"]["jitter"]["compute_time"]["status"] == "unavailable"
    assert report["pooled"]["jitter"]["compute_time"]["pair_coverage_fraction"] is None
