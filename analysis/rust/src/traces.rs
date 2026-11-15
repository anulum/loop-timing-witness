// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Independent numerical/source/service/capture joins over all original rows.

use crate::binding::BoundRun;
use crate::rows::Rows;
use std::collections::BTreeMap;

/// Original full trace counts and separate located findings.
pub(crate) struct TraceFindings {
    /// Derived asserted raw-spike population.
    pub raw_spikes: u64,
    /// Actual service rows, never equated generically with spikes.
    pub services: u64,
    /// Full original numerical oracle differences.
    pub numerical: Vec<String>,
    /// Original input/raw/projection source inconsistencies.
    pub source: Vec<String>,
    /// Selected one-neuron packet phase/population inconsistencies.
    pub service: Vec<String>,
    /// Original identity-to-witness availability/timestamp differences.
    pub joins: Vec<String>,
}

/// Compute independent full-row equality and exact-key observation joins.
pub(crate) fn analyze(run: &BoundRun, rows: &Rows) -> TraceFindings {
    let spikes: Vec<_> = rows["raw_spike_trace"]
        .iter()
        .filter(|row| row[2] == 1)
        .collect();
    TraceFindings {
        raw_spikes: spikes.len() as u64,
        services: rows["service_trace"].len() as u64,
        numerical: numerical(rows),
        source: source(rows),
        service: service(rows, &spikes),
        joins: joins(run, rows),
    }
}

/// Compare every numerical step with the original oracle.
fn numerical(rows: &Rows) -> Vec<String> {
    let mut findings = Vec::new();
    for (index, row) in rows["numerical_trace"].iter().enumerate() {
        if row[2..4] != rows["reference_projection"][index] {
            findings.push(format!("Numerical step {index}: original oracle differs."));
        }
    }
    findings
}

/// Compare the declared projection, the input stimulus and the raw spike phases with the traces.
fn source(rows: &Rows) -> Vec<String> {
    let mut findings = Vec::new();
    if rows["numerical_trace"]
        .iter()
        .zip(&rows["numerical_projection"])
        .any(|(row, projection)| row[2..4] != *projection)
    {
        findings
            .push("Declared numerical projection differs from the full identified trace.".into());
    }
    for (index, row) in rows["input_trace"].iter().enumerate() {
        if row[2..6] != rows["original_stimulus"][index] {
            findings.push(format!(
                "Input step {index}: original stimulus fields differ."
            ));
        }
    }
    for (index, row) in rows["raw_spike_trace"].iter().enumerate() {
        if row[2] != rows["reference_projection"][index][0]
            || row[3] != rows["input_trace"][index][6] + 1
        {
            findings.push(format!(
                "Raw step {index}: original spike or source phase differs."
            ));
        }
    }
    findings
}

/// Require one service packet per raw spike at the embedded and raw spike phases.
fn service(rows: &Rows, spikes: &[&Vec<i64>]) -> Vec<String> {
    let mut findings = Vec::new();
    let service = &rows["service_trace"];
    if service.len() != spikes.len() {
        findings.push("Service population differs from complete original raw spikes.".into());
    }
    for (index, row) in service.iter().enumerate() {
        if row[4] != row[3] + 1 {
            findings.push(format!(
                "Service {index}: embedded-to-observed phase differs."
            ));
        }
        if spikes.get(index).is_none_or(|spike| row[4] != spike[3] + 2) {
            findings.push(format!(
                "Service {index}: raw-spike-to-service phase differs."
            ));
        }
    }
    findings
}

/// Join every trace row to its channel's witness event by identity and tick.
fn joins(run: &BoundRun, rows: &Rows) -> Vec<String> {
    let mut findings = Vec::new();
    for (channel, name) in
        run.channels
            .iter()
            .zip(["input_trace", "numerical_trace", "service_trace"])
    {
        let observed: BTreeMap<_, _> = channel
            .events
            .iter()
            .map(|e| (i64::from(e.identity), e.ticks as i64))
            .collect();
        for row in &rows[name] {
            if observed.get(&row[1]) != row.last() {
                findings.push(format!(
                    "{} identity {}: witness unavailable or differs.",
                    channel.role, row[1]
                ));
            }
        }
    }
    findings
}
