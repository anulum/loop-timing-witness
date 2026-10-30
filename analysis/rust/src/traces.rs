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
    let mut result = TraceFindings {
        raw_spikes: 0,
        services: rows["service_trace"].len() as u64,
        numerical: Vec::new(),
        source: Vec::new(),
        service: Vec::new(),
        joins: Vec::new(),
    };
    for (index, row) in rows["numerical_trace"].iter().enumerate() {
        if row[2..4] != rows["reference_projection"][index] {
            result
                .numerical
                .push(format!("Numerical step {index}: original oracle differs."));
        }
    }
    if rows["numerical_trace"]
        .iter()
        .zip(&rows["numerical_projection"])
        .any(|(row, projection)| row[2..4] != *projection)
    {
        result
            .source
            .push("Declared numerical projection differs from the full identified trace.".into());
    }
    for (index, row) in rows["input_trace"].iter().enumerate() {
        if row[2..6] != rows["original_stimulus"][index] {
            result.source.push(format!(
                "Input step {index}: original stimulus fields differ."
            ));
        }
    }
    let spikes: Vec<_> = rows["raw_spike_trace"]
        .iter()
        .filter(|row| row[2] == 1)
        .collect();
    result.raw_spikes = spikes.len() as u64;
    for (index, row) in rows["raw_spike_trace"].iter().enumerate() {
        if row[2] != rows["reference_projection"][index][0]
            || row[3] != rows["input_trace"][index][6] + 1
        {
            result.source.push(format!(
                "Raw step {index}: original spike or source phase differs."
            ));
        }
    }
    let service = &rows["service_trace"];
    if service.len() != spikes.len() {
        result
            .service
            .push("Service population differs from complete original raw spikes.".into());
    }
    for (index, row) in service.iter().enumerate() {
        if row[4] != row[3] + 1 {
            result.service.push(format!(
                "Service {index}: embedded-to-observed phase differs."
            ));
        }
        if spikes.get(index).is_none_or(|spike| row[4] != spike[3] + 2) {
            result.service.push(format!(
                "Service {index}: raw-spike-to-service phase differs."
            ));
        }
    }
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
                result.joins.push(format!(
                    "{} identity {}: witness unavailable or differs.",
                    channel.role, row[1]
                ));
            }
        }
    }
    result
}
