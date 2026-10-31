// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native precision clock source binding

//! Actual native producer source and nanosecond/picosecond clock admission.

use crate::binding::BoundRun;
use crate::files::{FileRef, digest, receipt};
use crate::receipts::ProducerCompletion;
use serde::Deserialize;

/// Complete native driver clock schedule, distinct from an HDL testbench schedule.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Clock {
    scope: String,
    source_producer: FileRef,
    simulation_time_unit: String,
    simulation_time_precision: String,
    driver_half_period_precision_ticks: u64,
    capture_half_period_units: u64,
    drain_half_period_units: u64,
    first_input_tick: u64,
    requested_contiguous_steps: u64,
    expected_state_observation_offset_ticks: u64,
    dedicated_start_marker_tick: u64,
    dedicated_end_marker_tick: u64,
    tail_checked_after_edge_tick: u64,
    observed_final_counter: u64,
    capture_horizon_edges: u64,
}

/// Bind native driver/precision and compare common original edge predicates.
pub(crate) fn analyze(run: &BoundRun, done: &ProducerCompletion) -> Result<Vec<String>, String> {
    let c: Clock = receipt(&run.files["clock_schedule_ref"], "native clock")?;
    let _scope = c.scope;
    let values = [
        c.capture_half_period_units,
        c.drain_half_period_units,
        c.first_input_tick,
        c.requested_contiguous_steps,
        c.expected_state_observation_offset_ticks,
        c.dedicated_start_marker_tick,
        c.dedicated_end_marker_tick,
        c.tail_checked_after_edge_tick,
        c.observed_final_counter,
        c.capture_horizon_edges,
    ];
    if values.iter().any(|v| *v > 65535)
        || c.driver_half_period_precision_ticks > 65535
        || c.source_producer.byte_length > 65535
        || c.source_producer.sha256.len() != 64
        || !c
            .source_producer
            .sha256
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
    {
        return Err("Invalid complete actual receipt: native clock.".into());
    }
    let body = &run.sources["native/native_trial.cpp"];
    if c.source_producer.path != "native/native_trial.cpp"
        || c.source_producer.sha256 != digest(body)
        || c.source_producer.byte_length != body.len() as u64
        || c.simulation_time_precision != "1ps"
        || c.driver_half_period_precision_ticks != 5000
    {
        return Err("Actual native clock/source/precision differs.".into());
    }
    let n = u64::from(run.manifest.step_count);
    let mut findings = Vec::new();
    if run.files["declared_clock_schedule"] != run.files["clock_schedule_ref"] {
        findings.push("Root and tool receipt clock schedule bytes differ.".into());
    }
    if c.simulation_time_unit != "1ns" {
        findings.push("Actual source clock schedule differs: simulation_time_unit.".into());
    }
    for (name, actual, expected) in [
        ("capture_half_period_units", c.capture_half_period_units, 5),
        ("drain_half_period_units", c.drain_half_period_units, 5),
        ("first_input_tick", c.first_input_tick, 20),
        (
            "requested_contiguous_steps",
            c.requested_contiguous_steps,
            n,
        ),
        (
            "expected_state_observation_offset_ticks",
            c.expected_state_observation_offset_ticks,
            1,
        ),
        (
            "dedicated_start_marker_tick",
            c.dedicated_start_marker_tick,
            10,
        ),
        (
            "dedicated_end_marker_tick",
            c.dedicated_end_marker_tick,
            n + 30,
        ),
        (
            "tail_checked_after_edge_tick",
            c.tail_checked_after_edge_tick,
            n + 23,
        ),
        (
            "observed_final_counter",
            c.observed_final_counter,
            done.final_counter,
        ),
        (
            "capture_horizon_edges",
            c.capture_horizon_edges,
            run.manifest.capture_horizon_edges,
        ),
    ] {
        if actual != expected {
            findings.push(format!("Actual source clock schedule differs: {name}."));
        }
    }
    if done.final_counter <= n + 30 || done.final_counter >= run.manifest.capture_horizon_edges {
        findings.push("Full final counter does not fit the admitted post-marker horizon.".into());
    }
    Ok(findings)
}
