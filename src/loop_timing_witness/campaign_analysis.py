# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign statistics

"""Report every repeat, pool raw samples of valid repeats and state repeat spread."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .analyze_run import build_report
from .campaign_manifest import run_configuration
from .latency_jitter import JITTER_METHOD, jitter_pairs
from .run_analysis import distribution

if TYPE_CHECKING:
    from .campaign_manifest import CampaignInputs, CampaignRepeat

CAMPAIGN_REPORT_SCHEMA: Final = "loop-timing-witness.repeat-campaign-report.v1"
SPREAD_STATISTICS: Final = ("median_ticks", "p95_ticks", "p99_ticks", "p999_ticks", "maximum_ticks")

_Analysed = tuple[dict[str, Any], list[dict[str, int | str]]]


def _analyse_repeat(repeat: CampaignRepeat) -> tuple[dict[str, Any], _Analysed | None]:
    """Analyse one repeat with the per-run report and summarise its outcome.

    Parameters
    ----------
    repeat
        Loaded or refused campaign repeat.

    Returns
    -------
    tuple[dict[str, Any], tuple[dict[str, Any], list[dict[str, int | str]]] | None]
        Repeat entry for the campaign report, and the run report with its
        interval rows when the run could be analysed.
    """
    entry: dict[str, Any] = {
        "repeat_index": repeat.repeat_index,
        "run_manifest_sha256": repeat.run_manifest_sha256,
        "rebooted_before_run": repeat.rebooted_before_run,
        "run_id": None if repeat.inputs is None else repeat.inputs.manifest["run_id"],
        "status": "refused",
        "refusal": repeat.refusal,
        "invalid_reasons": [],
        "analysed_cycles": None,
        "duration_ticks": None,
        "intervals": None,
        "jitter": None,
        "control": None,
    }
    if repeat.inputs is None:
        return entry, None
    try:
        report, rows = build_report(repeat.inputs)
    except ValueError as error:
        entry["refusal"] = str(error)
        return entry, None
    events = report["events"]
    entry.update(
        {
            "status": "valid" if report["valid"] else "invalid",
            "invalid_reasons": report["invalid_reasons"],
            "analysed_cycles": events["cycle_count"],
            "duration_ticks": events["duration_ticks"],
            "intervals": events["intervals"],
            "jitter": events["jitter"],
            "control": events["control"],
        }
    )
    return entry, (report, rows)


def _pooled(valid: list[_Analysed], names: list[str]) -> dict[str, Any]:
    """Pool raw latency samples and within-run jitter pairs of valid repeats.

    Parameters
    ----------
    valid
        Run reports and interval rows of valid repeats.
    names
        Periodic interval names shared by every repeat.

    Returns
    -------
    dict[str, Any]
        Type-7 distributions over the concatenated samples, summed duration,
        cycle and pair accounting, and summed deadline counts.
    """
    latencies: dict[str, list[int]] = {name: [] for name in names}
    changes: dict[str, list[int]] = {name: [] for name in names}
    expected_pairs = 0
    for report, rows in valid:
        for row in rows:
            latencies[str(row["interval"])].append(int(row["ticks"]))
        for pair in jitter_pairs(rows):
            changes[str(pair["interval"])].append(int(pair["absolute_delta_ticks"]))
        expected_pairs += max(0, report["events"]["cycle_count"] - 1)
    duration = sum(report["events"]["duration_ticks"] for report, _ in valid)
    jitter: dict[str, Any] = {}
    for name in names:
        count = len(changes[name])
        jitter[name] = {
            **distribution(changes[name]),
            "status": "unavailable"
            if not count
            else "available"
            if count == expected_pairs
            else "partial",
            "expected_pair_count": expected_pairs,
            "missing_pair_count": expected_pairs - count,
            "pair_coverage_fraction": count / expected_pairs if expected_pairs else None,
            "duration_ticks": duration,
        }
    controls = [report["events"]["control"] for report, _ in valid]
    control = None
    if controls and controls[0] is not None:
        observed = sum(item["observed_deadlines"] for item in controls)
        misses = sum(item["deadline_misses"] for item in controls)
        control = {
            "observed_deadlines": observed,
            "deadline_misses": misses,
            "deadline_miss_rate": misses / observed if observed else None,
        }
    return {
        "repeat_count": len(valid),
        "run_ids": [report["run_id"] for report, _ in valid],
        "cycle_count": sum(report["events"]["cycle_count"] for report, _ in valid),
        "duration_ticks": duration,
        "intervals": {
            name: {**distribution(latencies[name]), "duration_ticks": duration} for name in names
        },
        "jitter_method": JITTER_METHOD,
        "jitter": jitter,
        "control": control,
    }


def _spread(valid: list[_Analysed], names: list[str], metric: str) -> dict[str, Any]:
    """State the range of each per-repeat statistic across valid repeats.

    Parameters
    ----------
    valid
        Run reports of valid repeats.
    names
        Periodic interval names.
    metric
        ``intervals`` for latency or ``jitter`` for adjacent-cycle change.

    Returns
    -------
    dict[str, Any]
        Minimum, maximum and range of each statistic. A statistic that any
        valid repeat could not compute, or with no valid repeat, is null.
    """
    result: dict[str, Any] = {}
    for name in names:
        result[name] = {}
        for statistic in SPREAD_STATISTICS:
            values = [report["events"][metric][name][statistic] for report, _ in valid]
            if not values or any(value is None for value in values):
                result[name][statistic] = {"minimum": None, "maximum": None, "range": None}
            else:
                result[name][statistic] = {
                    "minimum": min(values),
                    "maximum": max(values),
                    "range": max(values) - min(values),
                }
    return result


def _plan(
    inputs: CampaignInputs, entries: list[dict[str, Any]], domain: dict[str, Any] | None
) -> dict[str, Any]:
    """Compare the campaign with the measurement-domain run plan.

    Parameters
    ----------
    inputs
        Loaded campaign.
    entries
        Repeat entries in index order.
    domain
        Measurement-domain contract shared by loaded repeats, if any loaded.

    Returns
    -------
    dict[str, Any]
        Planned and declared repeat counts, cycles, validity counts, and the
        complete list of nonconformities. ``conforms`` is true only when that
        list is empty.
    """
    plan = None if domain is None else domain["design_contracts"]["run_plan"]
    planned_repeats = None if plan is None else plan["repeats"]
    planned_cycles = None if plan is None else plan["cycles_per_repeat"]
    nonconformities: list[str] = []
    if planned_repeats is None:
        nonconformities.append("no repeat could be loaded; the run plan is unavailable")
    elif len(entries) != planned_repeats:
        nonconformities.append(
            f"{len(entries)} repeats declared; the run plan requires {planned_repeats}"
        )
    nonconformities.extend(
        f"repeat {repeat.repeat_index} did not reboot before its run"
        for repeat in inputs.repeats
        if not repeat.rebooted_before_run
    )
    nonconformities.extend(
        f"repeat {entry['repeat_index']} is {entry['status']}"
        for entry in entries
        if entry["status"] != "valid"
    )
    analysed = {entry["analysed_cycles"] for entry in entries} - {None}
    if planned_cycles is not None and analysed and min(analysed) < planned_cycles:
        nonconformities.append(
            f"{min(analysed)} analysed cycles per repeat; the run plan requires {planned_cycles}"
        )
    return {
        "planned_repeats": planned_repeats,
        "planned_cycles_per_repeat": planned_cycles,
        "declared_repeats": len(entries),
        "valid_repeats": sum(entry["status"] == "valid" for entry in entries),
        "invalid_repeats": sum(entry["status"] == "invalid" for entry in entries),
        "refused_repeats": sum(entry["status"] == "refused" for entry in entries),
        "conforms": not nonconformities,
        "nonconformities": nonconformities,
    }


def build_campaign_report(inputs: CampaignInputs) -> dict[str, Any]:
    """Calculate the repeat campaign report from loaded repeats.

    Parameters
    ----------
    inputs
        Campaign whose loaded repeats share one configuration.

    Returns
    -------
    dict[str, Any]
        Every repeat with its outcome, pooled distributions of valid repeats,
        per-statistic spread between valid repeats, run-plan conformance and
        the evidence limits. Invalid and refused repeats stay listed and never
        contribute samples.
    """
    entries: list[dict[str, Any]] = []
    valid: list[_Analysed] = []
    analysed: list[_Analysed] = []
    for repeat in inputs.repeats:
        entry, result = _analyse_repeat(repeat)
        entries.append(entry)
        if result is not None:
            analysed.append(result)
            if entry["status"] == "valid":
                valid.append(result)
    loaded = [repeat.inputs for repeat in inputs.repeats if repeat.inputs is not None]
    first = loaded[0] if loaded else None
    names = list(analysed[0][0]["events"]["jitter"]) if analysed else []
    plan = _plan(inputs, entries, None if first is None else first.domain)
    source_kind = None if first is None else first.manifest["source"]["kind"]
    evidence_status = {
        None: "unavailable",
        "rtl_simulation": "simulation_only",
        "board": "board_declaration_unverified",
    }[source_kind]
    return {
        "schema": CAMPAIGN_REPORT_SCHEMA,
        "campaign_id": inputs.manifest["campaign_id"],
        "campaign_manifest_sha256": inputs.manifest_sha256,
        "evidence_status": evidence_status,
        "status": "complete" if plan["conforms"] else "incomplete",
        "configuration": None if first is None else run_configuration(first),
        "timebase_resolution_ns": None
        if first is None
        else first.domain["design_contracts"]["timebase"]["resolution_ns"],
        "plan": plan,
        "repeats": entries,
        "pooled": _pooled(valid, names),
        "spread": {
            "intervals": _spread(valid, names, "intervals"),
            "jitter": _spread(valid, names, "jitter"),
        },
        "limits": [
            (
                "Pooled distributions are computed from the concatenated raw samples of valid "
                "repeats; per-repeat percentiles are never averaged."
            ),
            "Adjacent-cycle jitter pairs never span two repeats.",
            (
                "Fault detection, time to safe state, tracking error and energy remain "
                "per-repeat results in the run reports and are not pooled here."
            ),
            "Spread is the range of each per-repeat statistic across valid repeats.",
            *(
                ["RTL simulation repeats are not board measurements."]
                if source_kind == "rtl_simulation"
                else []
            ),
        ],
    }
