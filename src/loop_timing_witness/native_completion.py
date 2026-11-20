# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — hash-bound native completion counters

"""Validate native completion receipts separately from incomplete captured events."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .event_stream import EVENT_RECORD
from .manifest_io import load_json_object, parse_bounded_json_object
from .run_analysis import analyse_events
from .validate_measurement_domain import schema_locations

if TYPE_CHECKING:
    from .event_stream import Event
    from .run_manifest import RunInputs

ROOT = Path(__file__).resolve().parent / "data"


def native_fault_schedule(fault: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the native fault declaration in the run manifest's schedule form.

    Parameters
    ----------
    fault
        Schema-valid native fault declaration.

    Returns
    -------
    list[dict[str, Any]]
        No entry for ``none``; otherwise the cycle, kind and delay periods.
    """
    if fault["kind"] == "none":
        return []
    return [
        {
            "cycle": fault["cycle"],
            "kind": fault["kind"],
            "delay_periods": fault["duration_periods"] if fault["kind"] == "delay" else 0,
        }
    ]


def _configuration_matches(
    native: dict[str, Any], manifest: dict[str, Any], event_count: int
) -> bool:
    """Tell whether the native receipt describes the declared run and its event file.

    Parameters
    ----------
    native
        Schema-valid native metadata.
    manifest
        Validated run declaration.
    event_count
        Number of actually decoded records, cycle and reference records alike.

    Returns
    -------
    bool
        Whether source kind, cycles, period, controller, plant, event file and
        configuration file all agree.
    """
    return not (
        native["source_kind"] != "rtl_simulation"
        or manifest["source"]["kind"] != "rtl_simulation"
        or native["cycles"] != manifest["cycle_count"]
        or native["period_ticks"] != manifest["sample_period_ticks"]
        or native["controller"] != manifest["controller"]["name"]
        or native["coefficients"] != manifest["controller"]["coefficients"]
        or native["thermal"] != (manifest["plant"]["name"] == "first_order_thermal")
        or native["result"]["samples"] > native["cycles"]
        or native["artifacts"]["events"]["sha256"] != manifest["files"]["events"]["sha256"]
        or native["artifacts"]["events"]["bytes"] != event_count * 16
        or native["artifacts"]["configuration"]["sha256"]
        not in {reference["sha256"] for reference in manifest["source"]["files"]}
    )


def _counters_match(
    native: dict[str, Any], manifest: dict[str, Any], event_count: int, control: dict[str, Any]
) -> bool:
    """Tell whether the native completion counters agree with the captured events.

    Parameters
    ----------
    native
        Schema-valid native metadata.
    manifest
        Validated run declaration.
    event_count
        Number of actually decoded records, cycle and reference records alike.
    control
        Full-run control analysis and sample-read count, before warm-up exclusion.

    Returns
    -------
    bool
        Whether records and overflow agree and, without overflow, so do misses,
        deadlines, sample reads and the safe state.
    """
    result = native["result"]
    return not (
        result["records"] != event_count
        or result["overflow"] != manifest["instrument"]["fifo_overflow_count"]
        or (
            not result["overflow"]
            and (
                result["misses"] != control["deadline_misses"]
                or native["cycles"] != control["observed_deadlines"]
                or result["samples"] != control["sample_read_events"]
                or result["safe"] != bool(control["safe_state_events"])
            )
        )
    )


def completion_statistics(
    content: bytes, manifest: dict[str, Any], event_count: int, control: dict[str, Any]
) -> dict[str, Any]:
    """Validate original native completion facts against the bound run declaration.

    Parameters
    ----------
    content
        Hash-verified native metadata bytes.
    manifest
        Validated run declaration.
    event_count
        Number of actually decoded records, cycle and reference records alike.
    control
        Full-run control analysis and sample-read count, before warm-up exclusion.

    Returns
    -------
    dict of str to Any
        Live native completion counters; they do not repair lost records.

    Raises
    ------
    ValueError
        If the native receipt contradicts its run or complete captured events.
    """
    native = parse_bounded_json_object(content, "native metadata")
    locations = schema_locations(native, load_json_object(ROOT / "native-run.schema.json"))
    if locations:
        message = f"native metadata {locations[0]}: does not satisfy the native run schema"
        raise ValueError(message)
    if native_fault_schedule(native["fault"]) != manifest["fault_schedule"]:
        message = "native metadata fault schedule does not match the run declaration"
        raise ValueError(message)
    if not _configuration_matches(native, manifest, event_count):
        message = "native metadata configuration does not match the run declaration"
        raise ValueError(message)
    if not _counters_match(native, manifest, event_count, control):
        message = "native completion counters do not match captured events"
        raise ValueError(message)
    result: dict[str, Any] = native["result"]
    return result


def attach_completion_statistics(
    inputs: RunInputs, report: dict[str, Any], events: tuple[Event, ...]
) -> None:
    """Attach verified native receipts and explicit lost-event inference limits.

    Parameters
    ----------
    inputs
        Schema-validated, hash-verified original inputs.
    report
        Event/series report being assembled by the public analyzer.
    events
        All decoded original events, including the warm-up prefix.

    Raises
    ------
    ValueError
        If native configuration/counters contradict the bound run.
    """
    if "native_metadata" in inputs.files:
        full = report["events"]
        if inputs.manifest["warmup_cycles"]:
            full, _ = analyse_events(
                events,
                inputs.domain["design_contracts"]["event_profiles"]["CONTROL"],
                inputs.manifest["cycle_count"],
                0,
            )
        control = dict(full["control"])
        control["sample_read_events"] = sum(event.name == "SAMPLE_READ" for event in events)
        # The native drain counts every record it took from the fabric, reference records too.
        report["native_completion"] = completion_statistics(
            inputs.files["native_metadata"],
            inputs.manifest,
            len(inputs.files["events"]) // EVENT_RECORD.size,
            control,
        )
        report["input_sha256"]["native_metadata"] = inputs.manifest["native_metadata"]["sha256"]
    if report["fifo_overflow_count"]:
        report["limits"].append(
            "FIFO overflow can remove actuator or deadline records; captured-event "
            "deadline misses do not establish actual controller misses."
        )
