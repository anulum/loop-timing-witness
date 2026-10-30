// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Reconcile actual producer clock, termination and channel declarations.

use crate::binding::BoundRun;
use crate::capture::Role;
use crate::files::decode;
use crate::receipts::ProducerCompletion;
use crate::traces::TraceFindings;

/// Require the complete original producer receipt and recompute all source counts/flags.
pub(crate) fn completion(
    run: &BoundRun,
    traces: &TraceFindings,
) -> Result<(ProducerCompletion, Vec<String>), String> {
    let d: ProducerCompletion = decode(&run.files["actual_completion"], "producer completion")?;
    let values = [
        d.requested_steps,
        d.observed_states,
        d.raw_spike_rows,
        d.raw_spikes,
        d.service_packets,
        d.simultaneous_spike_and_pending,
        d.tail_checked_after_edge_tick,
        d.counter_at_tail_check,
        d.final_counter,
    ];
    if values.iter().any(|v| *v > 65535) {
        return Err("Invalid complete actual receipt: producer completion.".into());
    }
    let n = u64::from(run.manifest.step_count);
    let mut failures = Vec::new();
    let c = &run.manifest.completion;
    for (name, differs) in [
        ("requested_steps", c.requested_steps != n),
        ("observed_states", c.observed_states != n),
        ("raw_spikes", c.raw_spikes != traces.raw_spikes),
        (
            "observed_service_packets",
            c.observed_service_packets != traces.services,
        ),
        ("pending_empty", c.pending_empty != d.pending_empty),
        (
            "service_valid_quiescent",
            c.service_valid_quiescent != d.service_quiescent,
        ),
        (
            "pipeline_quiescent",
            c.pipeline_quiescent != d.pipeline_quiescent,
        ),
        ("finalized", c.finalized != d.drain_complete),
    ] {
        if differs {
            failures.push(format!(
                "Root completion differs from actual source data: {name}."
            ));
        }
    }
    for (name, actual, expected) in [
        ("requested_steps", d.requested_steps, n),
        ("observed_states", d.observed_states, n),
        ("raw_spike_rows", d.raw_spike_rows, n),
        ("raw_spikes", d.raw_spikes, traces.raw_spikes),
        ("service_packets", d.service_packets, traces.services),
        (
            "simultaneous_spike_and_pending",
            d.simultaneous_spike_and_pending,
            0,
        ),
        (
            "tail_checked_after_edge_tick",
            d.tail_checked_after_edge_tick,
            n + 23,
        ),
        ("counter_at_tail_check", d.counter_at_tail_check, n + 24),
    ] {
        if actual != expected {
            failures.push(format!(
                "Actual selected completion predicate differs: {name}."
            ));
        }
    }
    if !d.pending_empty || !d.service_quiescent || !d.pipeline_quiescent || !d.drain_complete {
        failures.push("Actual tail/pipeline/service/drain is not finalized and quiescent.".into());
    }
    Ok((d, failures))
}

/// Compare all original channel metadata with decoded record and source counter values.
pub(crate) fn channels(run: &BoundRun, marker_finding: &str) -> Vec<String> {
    let mut failures = Vec::new();
    if run.counts.drop_counter_bits != 32 {
        failures.push("Actual counter width differs from the byte-pinned producer receipt.".into());
    }
    for (index, channel) in run.channels.iter().enumerate() {
        let d = &run.manifest.channels[index];
        let c = &run.counts.channels[index];
        for (name, differs) in [
            ("attempts", d.attempts != c.attempts),
            ("accepted", d.accepted != c.accepted),
            ("dropped", d.dropped != c.dropped),
            ("drained", d.drained != c.drained),
            ("overflowed", d.overflowed != c.overflowed),
            (
                "payload_records",
                d.payload_records != channel.events.len() as u64,
            ),
            (
                "marker_records",
                d.marker_records != channel.markers.len() as u64 / 16,
            ),
            (
                "drop_counter_saturated",
                d.drop_counter_saturated
                    != (c.dropped == (1_u64 << run.counts.drop_counter_bits) - 1),
            ),
        ] {
            if differs {
                failures.push(format!(
                    "{}: declaration differs from original capture: {name}.",
                    channel.role
                ));
            }
        }
        if channel.start != Some(10) || channel.end != Some(u64::from(run.manifest.step_count) + 30)
        {
            failures.push(format!("{}: {marker_finding}", channel.role));
        }
        if channel.role == Role::Input && channel.events.first().is_none_or(|e| e.ticks != 20) {
            failures
                .push("Input observation start differs from actual source clock schedule.".into());
        }
    }
    failures
}
