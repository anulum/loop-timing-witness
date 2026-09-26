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
from typing import Any

from event_stream import decode_events
from report_outputs import write_report
from run_analysis import analyse_events
from run_manifest import RunInputs, load_run
from run_series import energy_per_cycle, tracking_error

REPORT_SCHEMA = "loop-timing-witness.analysis-report.v1"


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
    scheduled = sorted(item["cycle"] for item in manifest["fault_schedule"])
    observed = sorted(event.cycle for event in events if event.name == "FAULT_INJECTED")
    if scheduled != observed:
        message = "fault schedule does not match captured FAULT_INJECTED events"
        raise ValueError(message)
    summary, cycle_rows = analyse_events(
        events,
        contracts["event_profiles"][manifest["profile"]],
        manifest["cycle_count"],
        manifest["warmup_cycles"],
    )
    if manifest["profile"] == "CONTROL":
        tracking = tracking_error(
            inputs.files.get("tracking"),
            manifest["cycle_count"],
            manifest["warmup_cycles"],
            manifest["plant"]["tracking_unit"],
        )
    else:
        tracking = {"status": "not_applicable", "reason": "COMPUTE has no control plant"}
    energy = energy_per_cycle(
        inputs.files.get("power"),
        events,
        manifest["profile"],
        manifest["warmup_cycles"],
        contracts["power_rails"],
    )
    duration_ticks = summary["duration_ticks"]
    for interval in summary["intervals"].values():
        interval["duration_ticks"] = duration_ticks
    if summary["control"] is not None:
        summary["control"]["sample_count"] = summary["control"]["observed_deadlines"]
        summary["control"]["duration_ticks"] = duration_ticks
    tracking["duration_ticks"] = duration_ticks
    energy["duration_ticks"] = duration_ticks
    if tracking["status"] != "available":
        tracking["sample_count"] = 0
    if energy["status"] == "unavailable":
        energy["sample_count"] = 0
    if manifest["profile"] == "CONTROL":
        anchor_count = summary["control"]["observed_deadlines"]
    else:
        anchor_count = sum(
            event.name == "INPUT_WRITE" and event.cycle >= manifest["warmup_cycles"]
            for event in events
        )
    complete = anchor_count == summary["cycle_count"]
    overflow = manifest["instrument"]["fifo_overflow_count"]
    missing_tracking = manifest["profile"] == "CONTROL" and tracking["status"] != "available"
    missing_energy = energy["status"] != "available"
    valid = complete and overflow == 0 and not missing_tracking and not missing_energy
    input_hashes = {
        name: item["sha256"] for name, item in manifest["files"].items() if item is not None
    }
    input_hashes["measurement_domain"] = manifest["measurement_domain"]["sha256"]
    input_hashes.update(
        {f"source:{item['path']}": item["sha256"] for item in manifest["source"]["files"]}
    )
    if manifest["hardware_artifacts"] is not None:
        input_hashes.update(
            {
                name: manifest["hardware_artifacts"][name]["sha256"]
                for name in ("bitstream", "firmware", "linux_image", "controller_binary")
            }
        )
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "run_id": manifest["run_id"],
        "started_utc": manifest["started_utc"],
        "source_kind": manifest["source"]["kind"],
        "evidence_status": "simulation_only"
        if manifest["source"]["kind"] == "rtl_simulation"
        else "board_declaration_unverified",
        "profile": manifest["profile"],
        "placement": manifest["placement"],
        "measurement_domain_sha256": manifest["measurement_domain"]["sha256"],
        "input_sha256": input_hashes,
        "timebase_resolution_ns": contracts["timebase"]["resolution_ns"],
        "instrument_floor_ticks": manifest["instrument"]["floor_ticks"],
        "fifo_overflow_count": overflow,
        "valid": valid,
        "invalid_reasons": [
            *(["event FIFO overflow"] if overflow else []),
            *(["missing cycle anchor events"] if not complete else []),
            *(["tracking series unavailable"] if missing_tracking else []),
            *(["power series unavailable"] if missing_energy else []),
        ],
        "events": summary,
        "tracking_error": tracking,
        "energy": energy,
        "limits": [
            (
                f"Timebase ticks resolve {contracts['timebase']['resolution_ns']} ns; "
                "interconnect offsets require calibration."
            ),
            "The plant is emulated; these are not physical-machine control results.",
            "Power rails share processor and fabric consumption. Energy is a window mean.",
        ],
    }
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
        inputs = load_run(args.manifest)
        report, cycle_rows = build_report(inputs)
        write_report(args.output_dir, report, cycle_rows)
    except (OSError, ValueError) as exc:
        print(f"run analysis: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"run analysis: PASS: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
