# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host run analysis command

"""Analyse a hash-bound witness run and write reproducible local reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .amp_report_completion import attach_amp_completion
from .event_stream import decode_events
from .host_load_receipt import attach_host_load
from .latency_jitter import JITTER_METHOD, summarise_jitter
from .native_completion import attach_completion_statistics
from .neural_run_dispatch import dispatch_analysis
from .report_outputs import write_report
from .run_analysis import analyse_events
from .run_manifest import RunInputs, load_run
from .run_report_fields import (
    REPORT_SCHEMA,
    anchor_count,
    energy_block,
    invalid_reasons,
    report_identity,
    report_limits,
    tracking_block,
)

if TYPE_CHECKING:
    from .event_stream import Event


# REPORT_SCHEMA stays importable from this module, where the report was first defined.
__all__ = [
    "REPORT_SCHEMA",
    "build_report",
    "check_fault_schedule",
    "events_block",
    "main",
    "share_duration",
]


def check_fault_schedule(manifest: dict[str, Any], events: tuple[Event, ...]) -> None:
    """Refuse a capture whose injected faults differ from the declared fault schedule.

    Parameters
    ----------
    manifest
        Schema-valid run manifest.
    events
        Decoded events of the run.

    Raises
    ------
    ValueError
        If the scheduled and captured ``FAULT_INJECTED`` cycles differ.
    """
    scheduled = sorted(item["cycle"] for item in manifest["fault_schedule"])
    observed = sorted(event.cycle for event in events if event.name == "FAULT_INJECTED")
    if scheduled != observed:
        message = "fault schedule does not match captured FAULT_INJECTED events"
        raise ValueError(message)


def share_duration(summary: dict[str, Any]) -> None:
    """Give every interval distribution and the control counts the block's ``duration_ticks``.

    Parameters
    ----------
    summary
        The ``events`` block, completed in place; the control counts also gain their
        ``sample_count``, the observed deadlines.
    """
    duration_ticks = summary["duration_ticks"]
    for interval in summary["intervals"].values():
        interval["duration_ticks"] = duration_ticks
    if summary["control"] is not None:
        summary["control"]["sample_count"] = summary["control"]["observed_deadlines"]
        summary["control"]["duration_ticks"] = duration_ticks


def events_block(
    manifest: dict[str, Any], contracts: dict[str, Any], events: tuple[Event, ...]
) -> tuple[dict[str, Any], list[dict[str, int | str]]]:
    """Build the report's ``events`` block from decoded events.

    The captured fault injections must match the declared fault schedule. The
    block holds the event and cycle counts, the observation span, the interval
    distributions, the control counts and the adjacent-cycle jitter, each with
    the shared ``duration_ticks``.

    Parameters
    ----------
    manifest
        Schema-valid run manifest.
    contracts
        Valid measurement-domain design contracts.
    events
        Decoded events of the run.

    Returns
    -------
    tuple[dict[str, Any], list[dict[str, int | str]]]
        The ``events`` block and the per-cycle interval rows.

    Raises
    ------
    ValueError
        If the fault schedule disagrees with the capture or an event order
        contradicts the interval and fault rules.
    """
    check_fault_schedule(manifest, events)
    profile = contracts["event_profiles"][manifest["profile"]]
    summary, cycle_rows = analyse_events(
        events, profile, manifest["cycle_count"], manifest["warmup_cycles"]
    )
    duration_ticks = summary["duration_ticks"]
    summary["jitter_method"] = JITTER_METHOD
    summary["jitter"] = summarise_jitter(
        cycle_rows,
        [
            str(interval["name"])
            for interval in profile["intervals"]
            if interval["name"] != "time_to_safe_state"
        ],
        summary["cycle_count"],
        duration_ticks,
    )
    share_duration(summary)
    return summary, cycle_rows


def build_report(inputs: RunInputs) -> tuple[dict[str, Any], list[dict[str, int | str]]]:
    """Calculate every report field from validated run inputs.

    Parameters
    ----------
    inputs
        Schema-valid manifest and bytes verified against their SHA-256 values.

    Returns
    -------
    tuple[dict[str, Any], list[dict[str, int | str]]]
        Report object and per-cycle interval table.

    Raises
    ------
    ValueError
        If binary events or auxiliary series contradict the run contract.
    """
    manifest = inputs.manifest
    contracts = inputs.domain["design_contracts"]
    events = decode_events(
        inputs.files["events"], contracts, manifest["profile"], manifest["cycle_count"]
    )
    summary, cycle_rows = events_block(manifest, contracts, events)
    tracking = tracking_block(inputs, events, summary["duration_ticks"])
    energy = energy_block(inputs, events, summary["duration_ticks"])
    complete = anchor_count(manifest, summary, events) == summary["cycle_count"]
    overflow = manifest["instrument"]["fifo_overflow_count"]
    missing_tracking = manifest["profile"] == "CONTROL" and tracking["status"] != "available"
    missing_energy = energy["status"] != "available"
    report: dict[str, Any] = {
        **report_identity(manifest, contracts),
        "fifo_overflow_count": overflow,
        "valid": complete and overflow == 0 and not missing_tracking and not missing_energy,
        "invalid_reasons": invalid_reasons(
            overflow,
            tracking,
            complete=complete,
            missing_tracking=missing_tracking,
            missing_energy=missing_energy,
        ),
        "events": summary,
        "tracking_error": tracking,
        "energy": energy,
        "limits": report_limits(contracts, tracking),
    }
    attach_completion_statistics(inputs, report, events)
    attach_amp_completion(inputs, report, events)
    attach_host_load(inputs, report)
    return report, cycle_rows


def main(argv: list[str] | None = None) -> int:
    """Run the host analysis command-line entry point.

    Parameters
    ----------
    argv
        Arguments without executable name, or ``None`` for ``sys.argv``.

    Returns
    -------
    int
        Zero after an atomic report write, one on an input or output error.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="versioned run manifest JSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="new report directory")
    args = parser.parse_args(argv)
    try:
        neural_status, manifest_bytes = dispatch_analysis(args.manifest, args.output_dir)
        if neural_status is not None:
            return neural_status
        inputs = load_run(args.manifest, manifest_bytes=manifest_bytes)
        report, cycle_rows = build_report(inputs)
        write_report(args.output_dir, report, cycle_rows)
    except (OSError, ValueError) as exc:
        print(f"run analysis: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"run analysis: PASS: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
