// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Complete closed run fields; all integer declarations retain their widths.

use crate::capture::ChannelDeclaration;
use crate::files::FileRef;
use serde::Deserialize;

/// All seven selected source-owner body pins, without duplicate map keys.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SourcePins {
    /// Maintained selected LIF RTL.
    #[serde(rename = "hdl/sc_lif_neuron.v")]
    pub lif: String,
    /// Maintained original source-owner testbench.
    #[serde(rename = "hdl/tb_sc_lif_neuron.v")]
    pub testbench: String,
    /// Maintained encoder RTL.
    #[serde(rename = "hdl/sc_aer_encoder.v")]
    pub encoder: String,
    /// Selected Python numerical reference.
    #[serde(rename = "src/sc_neurocore/neurons/fixed_point_lif.py")]
    pub model: String,
    /// Selected fixed-point constants.
    #[serde(rename = "src/sc_neurocore/constants.py")]
    pub constants: String,
    /// Source-owned public checker.
    #[serde(rename = "scripts/cosim_gen_and_check.py")]
    pub checker: String,
    /// Source-owned checker tests.
    #[serde(rename = "tests/test_cosim_gen_and_check.py")]
    pub checker_tests: String,
}

/// Original declared event meanings, never inferred from filenames.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Codes {
    /// Input application code.
    pub input_step_applied: u8,
    /// Observed state/raw-spike code.
    pub state_and_raw_spike_observed: u8,
    /// Actual encoder service code.
    pub encoder_packet_serviced: u8,
    /// Dedicated marker code.
    pub alignment_marker: u8,
}

/// Root status assertions later reconciled against actual source data.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Completion {
    /// Requested original inputs.
    pub requested_steps: u64,
    /// Reported state rows.
    pub observed_states: u64,
    /// Reported asserted raw spikes.
    pub raw_spikes: u64,
    /// Original packet count, including zero.
    pub observed_service_packets: u64,
    /// Original pending-empty assertion.
    pub pending_empty: bool,
    /// Original service valid quiescence.
    pub service_valid_quiescent: bool,
    /// Original observation pipeline status.
    pub pipeline_quiescent: bool,
    /// Original finalisation status.
    pub finalized: bool,
}

/// Closed run fields with separately admitted native source identity.
pub(crate) struct Manifest {
    /// Original profile name.
    pub profile: String,
    /// Simulation evidence class.
    pub evidence_class: String,
    /// Original run identifier.
    pub run_id: String,
    /// Source-owned exact epoch.
    pub epoch: u32,
    /// Full requested input/state population.
    pub step_count: u32,
    /// Original nominal per-channel capacity.
    pub fifo_capacity_records: u32,
    /// Exclusive full capture horizon.
    pub capture_horizon_edges: u64,
    /// Complete original source bodies.
    pub source_files: Vec<FileRef>,
    /// Complete selected model/checker/encoder pins.
    pub sc_body_pins: SourcePins,
    /// Actual original tool receipt.
    pub tool_receipt: FileRef,
    /// Complete identified original inputs.
    pub input_trace: FileRef,
    /// Complete identified observed numerical output.
    pub numerical_trace: FileRef,
    /// Declared original two-column numerical projection.
    pub numerical_projection: FileRef,
    /// Unchanged full original oracle.
    pub reference_projection: FileRef,
    /// Actual encoder service rows.
    pub service_trace: FileRef,
    /// Full input/state/service channel declarations.
    pub channels: [ChannelDeclaration; 3],
    /// Root completion claims.
    pub completion: Completion,
    /// Original declared simulator clock schedule.
    pub clock_schedule_ref: FileRef,
}
