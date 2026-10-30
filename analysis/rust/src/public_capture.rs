// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public capture accounting and timing report

//! Preserve the Python capture contract over the same complete native decoded bytes.

use crate::binding::BoundRun;
use crate::files::digest;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Complete public capture component and its independent located refusals.
pub(crate) struct Analysis {
    pub report: Value,
    pub findings: Vec<String>,
}

/// Preserve one complete original byte identity.
fn identity(raw: &[u8]) -> Value {
    json!({"sha256":digest(raw),"byte_length":raw.len()})
}

/// Match the public counter-accounting contract before source-specific assertions.
fn accounting(run: &BoundRun, index: usize) -> Vec<String> {
    let channel = &run.channels[index];
    let counts = &run.counts.channels[index];
    let saturated = counts.dropped == (1_u64 << run.counts.drop_counter_bits) - 1;
    let observed = channel.events.len() + channel.markers.len() / 16;
    let mut refusals = Vec::new();
    if counts
        .attempts
        .checked_sub(counts.accepted)
        .is_none_or(|difference| {
            if saturated {
                counts.dropped > difference
            } else {
                counts.dropped != difference
            }
        })
    {
        refusals.push(format!(
            "{}: attempted, accepted and dropped counts disagree",
            channel.role
        ));
    }
    if counts.overflowed != (counts.dropped > 0) {
        refusals.push(format!(
            "{}: overflow flag and drop counter disagree",
            channel.role
        ));
    }
    if counts.drained != counts.accepted {
        refusals.push(format!(
            "{}: accepted records were not completely drained",
            channel.role
        ));
    }
    if observed as u64 != counts.drained {
        refusals.push(format!(
            "{}: exported records differ from drain count",
            channel.role
        ));
    }
    if counts.overflowed || counts.dropped > 0 {
        refusals.push(format!("{}: capture lost records", channel.role));
    }
    if saturated {
        refusals.push(format!(
            "{}: drop counter is a lower bound at saturation",
            channel.role
        ));
    }
    refusals
}

/// Correlate every available same-identity pair without repairing losses or phases.
fn timing(run: &BoundRun) -> (Vec<Value>, Vec<String>) {
    let mut refusals = Vec::new();
    let mut markers = BTreeSet::new();
    for channel in &run.channels {
        if channel.start.is_none() || channel.end.is_none() {
            refusals.push(format!("{}: missing alignment marker", channel.role));
        } else if channel
            .end
            .is_some_and(|end| end >= run.manifest.capture_horizon_edges)
        {
            refusals.push(format!(
                "{}: end marker exceeds capture horizon",
                channel.role
            ));
        }
        markers.insert((channel.start, channel.end));
    }
    if markers.len() != 1 {
        refusals.push("channels: alignment marker ticks differ".into());
    }
    for channel in &run.channels[..2] {
        if channel
            .events
            .iter()
            .map(|event| event.identity)
            .collect::<Vec<_>>()
            != (0..run.manifest.step_count).collect::<Vec<_>>()
        {
            refusals.push(format!(
                "{}: step population differs from requested identities",
                channel.role
            ));
        }
    }
    let states: BTreeMap<_, _> = run.channels[1]
        .events
        .iter()
        .map(|event| (event.identity, event.ticks))
        .collect();
    let mut previous = None;
    let mut intervals = Vec::new();
    for event in &run.channels[0].events {
        if previous.is_some_and(|tick| event.ticks != tick + 1) {
            refusals.push(format!(
                "input step {}: application cadence differs from one tick",
                event.identity
            ));
        }
        previous = Some(event.ticks);
        if let Some(observed) = states.get(&event.identity) {
            let interval = i128::from(*observed) - i128::from(event.ticks);
            intervals.push(json!({
                "identity":event.identity,"applied_tick":event.ticks,
                "observed_tick":observed,"interval_ticks":interval,
            }));
            if interval != 1 {
                refusals.push(format!(
                    "state step {}: observation phase differs from one tick",
                    event.identity
                ));
            }
        }
    }
    (intervals, refusals)
}

/// Report complete original projections, actual drop bounds and located timing findings.
pub(crate) fn analyze(run: &BoundRun) -> Analysis {
    let mut refusals = Vec::new();
    let mut channels = Vec::new();
    for (index, channel) in run.channels.iter().enumerate() {
        let counts = &run.counts.channels[index];
        let account = accounting(run, index);
        refusals.extend(account.iter().cloned());
        let original_capture = &run.files[&format!("{}_capture", channel.role)];
        let original_payload = &run.files[&format!("{}_payload", channel.role)];
        let original_markers = &run.files[&format!("{}_markers", channel.role)];
        if original_payload != &channel.payload {
            refusals.push(format!(
                "{}: payload file differs from original capture projection",
                channel.role
            ));
        }
        if original_markers != &channel.markers {
            refusals.push(format!(
                "{}: marker file differs from original capture projection",
                channel.role
            ));
        }
        let population = if index == 2 {
            run.manifest.completion.observed_service_packets
        } else {
            u64::from(run.manifest.step_count)
        };
        if counts.attempts != population + 2 {
            refusals.push(format!(
                "{}: attempts differ from requested data and alignment markers",
                channel.role
            ));
        }
        let events: Vec<_> = channel.events.iter().map(|event| json!({
            "identity":event.identity,"ticks":event.ticks,"record_byte_offset":event.byte_offset,
        })).collect();
        channels.push(json!({
            "role":channel.role,
            "sources":{
                "capture":identity(original_capture),"payload":identity(original_payload),
                "markers":identity(original_markers),
            },
            "derived_projections":{"payload":identity(&channel.payload),"markers":identity(&channel.markers)},
            "start_marker_tick":channel.start,"end_marker_tick":channel.end,
            "observed_data_records":channel.events.len(),
            "observed_total_records":channel.events.len()+channel.markers.len()/16,
            "attempts":counts.attempts,"accepted":counts.accepted,"drained":counts.drained,
            "overflowed":counts.overflowed,
            "drop_counter":{"bits":run.counts.drop_counter_bits,"value":counts.dropped,
                "lower_bound":counts.dropped,"exact":counts.dropped!=(1_u64<<run.counts.drop_counter_bits)-1},
            "events":events,"accounting_refusals":account,
        }));
    }
    let (intervals, step_refusals) = timing(run);
    refusals.extend(step_refusals.iter().cloned());
    if run.channels[2]
        .events
        .iter()
        .map(|event| u64::from(event.identity))
        .collect::<Vec<_>>()
        != (0..run.manifest.completion.observed_service_packets).collect::<Vec<_>>()
    {
        refusals.push("service: packet population differs from requested identities".into());
    }
    Analysis {
        report: json!({
            "scope":"capture","unit":"shared-counter ticks",
            "requested":{"step_count":run.manifest.step_count,
                "service_packets":run.manifest.completion.observed_service_packets,
                "capture_horizon_edges":run.manifest.capture_horizon_edges},
            "counter_receipt":identity(&run.files["counter_receipt"]),
            "channels":channels,"step_observations":intervals,
            "step_refusals":step_refusals,"refusals":refusals,
        }),
        findings: refusals,
    }
}
