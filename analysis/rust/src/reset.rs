// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Complete actual abandoned-prefix/reset receipt interpretation, distinct from epoch0.

use crate::binding::BoundRun;
use crate::files::receipt;
use crate::rows;
use serde::Deserialize;

/// Actual closed joint-reset public-port receipt.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Reset {
    /// Original abandoned source epoch.
    abandoned_epoch: u64,
    /// Actual fresh source epoch.
    next_epoch: u64,
    /// Original observed prefix inputs.
    prefix_inputs: u64,
    /// Original observed prefix states.
    prefix_states: u64,
    /// Original observed prefix raw rows.
    prefix_raw_rows: u64,
    /// Original observed prefix spikes.
    prefix_raw_spikes: u64,
    /// Original observed prefix packets.
    prefix_services: u64,
    /// Actual pre-reset common counter.
    counter_before_reset: u64,
    /// Actual three pre-reset attempts.
    prefix_attempts: [u64; 3],
    /// Actual three pre-reset accepts.
    prefix_accepted: [u64; 3],
    /// Actual pending spike before reset.
    encoder_pending_before_reset: bool,
    /// Actual pre-reset FIFO observations.
    all_three_fifos_queued_before_reset: bool,
    /// Original source inputs not yet committed to FIFO.
    uncommitted_input_records_before_reset: u64,
    /// Actual reset common counter.
    reset_counter: u64,
    /// Actual reset attempt counters.
    reset_attempts: [u64; 3],
    /// Actual reset accepted counters.
    reset_accepted: [u64; 3],
    /// Actual reset service ordinal.
    reset_service_ordinal: u64,
    /// Actual post-reset empty FIFO observations.
    all_three_fifos_empty_after_reset: bool,
    /// Actual public model/encoder valid/ordinal/busy quiescence.
    model_and_encoder_quiescent_after_reset: bool,
}

/// Original abandoned traces of the reset prefix.
struct Abandoned {
    /// Source input rows.
    input: Vec<rows::Row>,
    /// Numerical state rows.
    state: Vec<rows::Row>,
    /// Raw spike rows.
    spikes: Vec<rows::Row>,
    /// Encoder service rows.
    service: Vec<rows::Row>,
}

/// Recompute the actual complete reset/prefix claim without inventing hidden state.
pub(crate) fn analyze(run: &BoundRun, original_rows: &rows::Rows) -> Result<Vec<String>, String> {
    let Some(raw) = run.files.get("reset_epoch_receipt") else {
        return Ok(Vec::new());
    };
    let r = admit(raw)?;
    let a = abandoned(run)?;
    let mut failures = prefix_failures(&a, original_rows);
    if !a.service.is_empty() {
        failures.push("Abandoned encoder pending spike was already serviced before reset.".into());
    }
    for (name, differs) in prefix_predicates(&r, run, &a)
        .into_iter()
        .chain(reset_predicates(&r))
    {
        if differs {
            failures.push(format!("Actual joint reset predicate differs: {name}."));
        }
    }
    if a.input.len() < 2
        || a.state.len() != a.input.len() - 1
        || a.spikes.len() != a.state.len()
        || r.prefix_raw_spikes != 1
        || !a.service.is_empty()
    {
        failures.push(
            "Actual prefix did not establish the selected queued/inflight/pending reset.".into(),
        );
    }
    Ok(failures)
}

/// Decode the closed reset receipt and require every count within 16 bits.
fn admit(raw: &[u8]) -> Result<Reset, String> {
    let r: Reset = receipt(raw, "actual joint reset")?;
    let counts = [
        r.abandoned_epoch,
        r.next_epoch,
        r.prefix_inputs,
        r.prefix_states,
        r.prefix_raw_rows,
        r.prefix_raw_spikes,
        r.prefix_services,
        r.counter_before_reset,
        r.uncommitted_input_records_before_reset,
        r.reset_counter,
        r.reset_service_ordinal,
    ];
    if counts
        .iter()
        .chain(r.prefix_attempts.iter())
        .chain(r.prefix_accepted.iter())
        .chain(r.reset_attempts.iter())
        .chain(r.reset_accepted.iter())
        .any(|v| *v > 65535)
    {
        return Err("Invalid complete actual receipt: actual joint reset.".into());
    }
    Ok(r)
}

/// Decode the four abandoned traces and require epoch zero and consecutive identities.
fn abandoned(run: &BoundRun) -> Result<Abandoned, String> {
    let input = rows::decode(&run.files["abandoned_input_trace"], 7, "abandoned input")?;
    let state = rows::decode(
        &run.files["abandoned_numerical_trace"],
        5,
        "abandoned numerical",
    )?;
    let spikes = rows::decode(
        &run.files["abandoned_raw_spike_trace"],
        4,
        "abandoned raw_spike",
    )?;
    let service = rows::decode(
        &run.files["abandoned_service_trace"],
        5,
        "abandoned service",
    )?;
    for (name, data) in [
        ("input", &input),
        ("numerical", &state),
        ("raw_spike", &spikes),
        ("service", &service),
    ] {
        if data
            .iter()
            .enumerate()
            .any(|(i, row)| row[..2] != [0, i as i64])
        {
            return Err(format!(
                "Original abandoned epoch/identity sequence differs: {name}."
            ));
        }
    }
    Ok(Abandoned {
        input,
        state,
        spikes,
        service,
    })
}

/// Compare every abandoned row with the original fixture, oracle and source phase.
fn prefix_failures(a: &Abandoned, original_rows: &rows::Rows) -> Vec<String> {
    let original = &original_rows["original_stimulus"];
    let expected = &original_rows["reference_projection"];
    let mut failures = Vec::new();
    for (i, row) in a.input.iter().enumerate() {
        if original.get(i).is_none_or(|v| row[2..6] != *v) || row[6] != 20 + i as i64 {
            failures.push(format!(
                "Abandoned input {i}: original fixture or source phase differs."
            ));
        }
    }
    for (i, row) in a.state.iter().enumerate() {
        if expected.get(i).is_none_or(|v| row[2..4] != *v) || row[4] != 21 + i as i64 {
            failures.push(format!(
                "Abandoned numerical {i}: original oracle or source phase differs."
            ));
        }
    }
    for (i, row) in a.spikes.iter().enumerate() {
        if expected.get(i).is_none_or(|v| row[2] != v[0]) || row[3] != 21 + i as i64 {
            failures.push(format!(
                "Abandoned raw spike {i}: original flag or source phase differs."
            ));
        }
    }
    failures
}

/// Return each named prefix predicate and whether the receipt contradicts the traces.
fn prefix_predicates(r: &Reset, run: &BoundRun, a: &Abandoned) -> [(&'static str, bool); 11] {
    let observed_spikes: i128 = a.spikes.iter().map(|row| i128::from(row[2])).sum();
    let actual_counters = [a.input.len() as u64, a.state.len() as u64, 1];
    [
        ("abandoned_epoch", r.abandoned_epoch != 0),
        ("next_epoch", r.next_epoch != u64::from(run.manifest.epoch)),
        ("prefix_inputs", r.prefix_inputs != a.input.len() as u64),
        ("prefix_states", r.prefix_states != a.state.len() as u64),
        (
            "prefix_raw_rows",
            r.prefix_raw_rows != a.spikes.len() as u64,
        ),
        (
            "prefix_raw_spikes",
            i128::from(r.prefix_raw_spikes) != observed_spikes,
        ),
        (
            "prefix_services",
            r.prefix_services != a.service.len() as u64,
        ),
        (
            "counter_before_reset",
            r.counter_before_reset != 20 + a.input.len() as u64,
        ),
        (
            "uncommitted_input_records_before_reset",
            r.uncommitted_input_records_before_reset != 1,
        ),
        ("prefix_attempts", r.prefix_attempts != actual_counters),
        ("prefix_accepted", r.prefix_accepted != actual_counters),
    ]
}

/// Return each named reset predicate and whether the receipt contradicts it.
fn reset_predicates(r: &Reset) -> [(&'static str, bool); 8] {
    [
        ("reset_counter", r.reset_counter != 0),
        ("reset_attempts", r.reset_attempts != [0, 0, 0]),
        ("reset_accepted", r.reset_accepted != [0, 0, 0]),
        ("reset_service_ordinal", r.reset_service_ordinal != 0),
        (
            "encoder_pending_before_reset",
            !r.encoder_pending_before_reset,
        ),
        (
            "all_three_fifos_queued_before_reset",
            !r.all_three_fifos_queued_before_reset,
        ),
        (
            "all_three_fifos_empty_after_reset",
            !r.all_three_fifos_empty_after_reset,
        ),
        (
            "model_and_encoder_quiescent_after_reset",
            !r.model_and_encoder_quiescent_after_reset,
        ),
    ]
}
