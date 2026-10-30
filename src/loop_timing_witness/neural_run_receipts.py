# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural run observations

"""Reconcile actual tool, channel counter and termination receipts with full data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .manifest_io import parse_json_object
from .neural_event_stream import NEURAL_RECORD
from .neural_run_clock import FLAG, UNSIGNED, analyze_source_clock, decode_actual_receipt
from .neural_run_source_receipts import analyze_source_receipts

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun
    from .neural_run_traces import NeuralTraceAnalysis

START_MARKER_TICK = 10
FIRST_INPUT_TICK = 20
SOURCE_DROP_COUNTER_BITS = 32


@dataclass(frozen=True, slots=True)
class NeuralReceiptFindings:
    """Independent source, clock, completion, capture and publication observations.

    Attributes
    ----------
    source, clock, completion, capture
        Existing complete receipt findings, separated by their owning contract.
    publication
        Actual native execution/final stdout status, in addition to drain status.
    """

    source: tuple[str, ...]
    clock: tuple[str, ...]
    completion: tuple[str, ...]
    capture: tuple[str, ...]
    publication: tuple[str, ...]


def _completion_findings(
    run: BoundNeuralRun,
    traces: NeuralTraceAnalysis,
    completion: dict[str, Any],
) -> tuple[str, ...]:
    """Reconcile actual completion and root populations with original trace data.

    Parameters
    ----------
    run
        Original root completion declarations.
    traces
        Independent full source trace counts.
    completion
        Admitted actual producer receipt.

    Returns
    -------
    tuple[str, ...]
        Full population, non-coalescence and termination inconsistencies.
    """
    count = run.manifest["step_count"]
    failures = []
    status = {
        "requested_steps": count,
        "observed_states": count,
        "raw_spikes": traces.raw_spikes,
        "observed_service_packets": traces.service_packets,
        "pending_empty": completion["pending_empty"],
        "service_valid_quiescent": completion["service_quiescent"],
        "pipeline_quiescent": completion["pipeline_quiescent"],
        "finalized": completion["drain_complete"],
    }
    for name, expected in status.items():
        if run.manifest["completion"][name] != expected:
            failures.append(f"Root completion differs from actual source data: {name}.")
    actual_counts = {
        "requested_steps": count,
        "observed_states": count,
        "raw_spike_rows": count,
        "raw_spikes": traces.raw_spikes,
        "service_packets": traces.service_packets,
        "simultaneous_spike_and_pending": 0,
        "tail_checked_after_edge_tick": count + 23,
        "counter_at_tail_check": count + 24,
    }
    for name, expected in actual_counts.items():
        if completion[name] != expected:
            failures.append(f"Actual selected completion predicate differs: {name}.")
    if any(
        completion[name] is not True
        for name in ("pending_empty", "service_quiescent", "pipeline_quiescent", "drain_complete")
    ):
        failures.append("Actual tail/pipeline/service/drain is not finalized and quiescent.")
    return tuple(failures)


def _channel_findings(run: BoundNeuralRun) -> tuple[str, ...]:
    """Compare each declared population, saturation field and marker with exports.

    Parameters
    ----------
    run
        Whole original bound capture and manifest channel declarations.

    Returns
    -------
    tuple[str, ...]
        Original field, population, marker and starting-phase inconsistencies.
    """
    count = run.manifest["step_count"]
    failures = []
    if run.capture.counts[0].drop_counter_bits != SOURCE_DROP_COUNTER_BITS:
        failures.append("Actual counter width differs from the byte-pinned producer receipt.")
    for index, declaration in enumerate(run.manifest["channels"]):
        channel, counts, accounting = (
            run.capture.channels[index],
            run.capture.counts[index],
            run.capture.accounting[index],
        )
        values = {
            name: getattr(counts, name)
            for name in ("attempts", "accepted", "dropped", "drained", "overflowed")
        }
        values.update(
            {
                "payload_records": len(channel.events),
                "marker_records": len(channel.marker_bytes) // NEURAL_RECORD.size,
                "drop_counter_saturated": not accounting.drop_count_exact,
            }
        )
        for name, expected in values.items():
            if declaration[name] != expected:
                failures.append(
                    f"{channel.role}: declaration differs from original capture: {name}."
                )
        if channel.start_tick != START_MARKER_TICK or channel.end_tick != count + 30:
            failures.append(f"{channel.role}: markers differ from actual selected source schedule.")
        first = channel.events[0].ticks if channel.events else None
        if channel.role == "input" and first != FIRST_INPUT_TICK:
            failures.append("Input observation start differs from actual source clock schedule.")
    return tuple(failures)


def analyze_receipt_dimensions(
    run: BoundNeuralRun, traces: NeuralTraceAnalysis
) -> NeuralReceiptFindings:
    """Recompute full source, clock, counter, horizon and finalisation predicates.

    Parameters
    ----------
    run
        Complete bound original manifest, source and capture bytes.
    traces
        Independent original trace counts and findings.

    Returns
    -------
    NeuralReceiptFindings
        Independent actual receipt findings. Recorded checker metadata remains
        historical; its source-binding status is not a fresh checker execution.

    Raises
    ------
    ValueError
        If receipt shape or nested original source binding is ambiguous.
    """
    completion = decode_actual_receipt(
        run.files["actual_completion"],
        "producer completion",
        {
            **dict.fromkeys(
                (
                    "requested_steps",
                    "observed_states",
                    "raw_spike_rows",
                    "raw_spikes",
                    "service_packets",
                    "simultaneous_spike_and_pending",
                    "tail_checked_after_edge_tick",
                    "counter_at_tail_check",
                    "final_counter",
                ),
                UNSIGNED,
            ),
            **dict.fromkeys(
                ("pending_empty", "service_quiescent", "pipeline_quiescent", "drain_complete"), FLAG
            ),
        },
    )
    source = analyze_source_receipts(run, traces)
    publication: tuple[str, ...] = ()
    runtime = parse_json_object(run.files["compiler_simulator_runtime"], "native runtime")
    if (
        runtime["jobs"][4]["returncode"] != 0
        or run.files["native_job_4_stdout"] != b"NATIVE_JOINT_EXPORT_COMPLETE\n"
        or run.files["native_job_4_stderr"]
    ):
        publication = ("Actual native execution/publication did not finalise cleanly.",)
    return NeuralReceiptFindings(
        source,
        analyze_source_clock(run, completion),
        _completion_findings(run, traces, completion),
        _channel_findings(run),
        publication,
    )
