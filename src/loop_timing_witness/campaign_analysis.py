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
from .campaign_pooling import Analysed, pooled, spread

if TYPE_CHECKING:
    from .campaign_manifest import CampaignInputs, CampaignRepeat

CAMPAIGN_REPORT_SCHEMA: Final = "loop-timing-witness.repeat-campaign-report.v1"
_EVIDENCE_STATUS: Final = {
    None: "unavailable",
    "rtl_simulation": "simulation_only",
    "board": "board_declaration_unverified",
}


def _printable(refusal: str | None) -> str | None:
    r"""Return a refusal as the report holds it, as UTF-8 text.

    A refusal can name a path with bytes that are not UTF-8, or a repeated JSON
    member name holding an unpaired surrogate. Each such code point is written
    as its backslash escape, as the command prints a refusal.

    Parameters
    ----------
    refusal
        Refusal text, or ``None``.

    Returns
    -------
    str | None
        Text with every unpaired surrogate as ``\udXXX``, or ``None``.
    """
    return None if refusal is None else refusal.encode("utf-8", "backslashreplace").decode()


def _analyse_repeat(repeat: CampaignRepeat) -> tuple[dict[str, Any], Analysed | None]:
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
        "refusal": _printable(repeat.refusal),
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
        entry["refusal"] = _printable(str(error))
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
    nonconformities = _nonconformities(inputs, entries, planned_repeats, planned_cycles)
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


def _nonconformities(
    inputs: CampaignInputs,
    entries: list[dict[str, Any]],
    planned_repeats: int | None,
    planned_cycles: int | None,
) -> list[str]:
    """List every way the campaign departs from the measurement-domain run plan.

    Parameters
    ----------
    inputs
        Loaded campaign.
    entries
        Repeat entries in index order.
    planned_repeats
        Repeats the run plan requires, or ``None`` when no repeat could be loaded.
    planned_cycles
        Analysed cycles per repeat the run plan requires, or ``None``.

    Returns
    -------
    list[str]
        Nonconformities in report order: plan availability or repeat count, reboots,
        repeat outcomes, then the analysed cycle count.
    """
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
    return nonconformities


def _analyse_repeats(
    inputs: CampaignInputs,
) -> tuple[list[dict[str, Any]], list[Analysed], list[Analysed]]:
    """Analyse every repeat in index order.

    Parameters
    ----------
    inputs
        Loaded campaign.

    Returns
    -------
    tuple
        Every repeat's entry, the analysed repeats and the valid repeats among them.
    """
    entries: list[dict[str, Any]] = []
    analysed: list[Analysed] = []
    valid: list[Analysed] = []
    for repeat in inputs.repeats:
        entry, result = _analyse_repeat(repeat)
        entries.append(entry)
        if result is not None:
            analysed.append(result)
            if entry["status"] == "valid":
                valid.append(result)
    return entries, analysed, valid


def _campaign_limits(source_kind: str | None) -> list[str]:
    """Return the stated limits of the campaign report's claims.

    Parameters
    ----------
    source_kind
        Source kind of the first loaded repeat, or ``None``.

    Returns
    -------
    list[str]
        Pooling, pairing, per-repeat and spread limits, and the simulation limit for RTL runs.
    """
    return [
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
    ]


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

    Raises
    ------
    ValueError
        If the valid repeats together span more than the 64-bit tick range.
    """
    entries, analysed, valid = _analyse_repeats(inputs)
    loaded = [repeat.inputs for repeat in inputs.repeats if repeat.inputs is not None]
    first = loaded[0] if loaded else None
    names = list(analysed[0][0]["events"]["jitter"]) if analysed else []
    plan = _plan(inputs, entries, None if first is None else first.domain)
    source_kind = None if first is None else first.manifest["source"]["kind"]
    return {
        "schema": CAMPAIGN_REPORT_SCHEMA,
        "campaign_id": inputs.manifest["campaign_id"],
        "campaign_manifest_sha256": inputs.manifest_sha256,
        "evidence_status": _EVIDENCE_STATUS[source_kind],
        "status": "complete" if plan["conforms"] else "incomplete",
        "configuration": None if first is None else run_configuration(first),
        "timebase_resolution_ns": None
        if first is None
        else first.domain["design_contracts"]["timebase"]["resolution_ns"],
        "plan": plan,
        "repeats": entries,
        "pooled": pooled(valid, names),
        "spread": {
            "intervals": spread(valid, names, "intervals"),
            "jitter": spread(valid, names, "jitter"),
        },
        "limits": _campaign_limits(source_kind),
    }
