// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Closed original auxiliary references and source-producer receipt grammar.

use crate::files::FileRef;
use serde::Deserialize;

/// Original closed tool receipt for epoch0.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Tool {
    /// Actual original scope text.
    pub scope: String,
    /// Actual compiler/simulator receipts.
    pub compiler_simulator_runtime: FileRef,
    /// Actual recorded model/checker receipt.
    pub source_owned_public_model_checker: FileRef,
    /// Actual source counter snapshot.
    pub counter_receipt: FileRef,
    /// Full original parallel raw-spike trace.
    pub raw_spike_trace: FileRef,
    /// Unchanged original stimulus.
    pub original_stimulus: FileRef,
    /// Actual producer completion receipt.
    pub actual_completion: FileRef,
    /// Original detailed trial analysis, separately bounded.
    pub existing_trial_analysis: FileRef,
    /// Actual simulator edge schedule.
    pub declared_clock_schedule: FileRef,
}

/// All four abandoned-prefix references; missing empty service is still invalid.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PrefixRefs {
    /// Actual identified abandoned inputs.
    pub input: FileRef,
    /// Actual observed abandoned numerical rows.
    pub numerical: FileRef,
    /// Actual original abandoned raw spikes.
    pub raw_spike: FileRef,
    /// Present original pre-service export.
    pub service: FileRef,
}

/// Closed epoch1 tool receipt with actual reset/prefix proof.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ResetTool {
    /// Actual original scope text.
    pub scope: String,
    /// Actual compiler/simulator receipts.
    pub compiler_simulator_runtime: FileRef,
    /// Actual recorded model/checker receipt.
    pub source_owned_public_model_checker: FileRef,
    /// Actual source counter snapshot.
    pub counter_receipt: FileRef,
    /// Full original parallel raw-spike trace.
    pub raw_spike_trace: FileRef,
    /// Unchanged original stimulus.
    pub original_stimulus: FileRef,
    /// Actual producer completion receipt.
    pub actual_completion: FileRef,
    /// Original detailed trial analysis.
    pub existing_trial_analysis: FileRef,
    /// Actual simulator edge schedule.
    pub declared_clock_schedule: FileRef,
    /// Actual original HDL reset receipt.
    pub reset_epoch_receipt: FileRef,
    /// Every actual abandoned trace reference.
    pub abandoned_prefix_traces: PrefixRefs,
}

/// Actual producer completion, later reconciled with original data.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProducerCompletion {
    /// Requested input population.
    pub requested_steps: u64,
    /// Observed numerical rows.
    pub observed_states: u64,
    /// Observed original raw rows.
    pub raw_spike_rows: u64,
    /// Original asserted raw-spike count.
    pub raw_spikes: u64,
    /// Actual service packets.
    pub service_packets: u64,
    /// Actual selected coalescence monitor.
    pub simultaneous_spike_and_pending: u64,
    /// Source tail sampling edge.
    pub tail_checked_after_edge_tick: u64,
    /// Actual counter at tail check.
    pub counter_at_tail_check: u64,
    /// Actual complete counter at drain termination.
    pub final_counter: u64,
    /// Original pending status.
    pub pending_empty: bool,
    /// Original service status.
    pub service_quiescent: bool,
    /// Original observation pipeline status.
    pub pipeline_quiescent: bool,
    /// Original accepted-record drain status.
    pub drain_complete: bool,
}
