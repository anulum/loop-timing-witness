// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public neural carrier declarations

//! Typed public carrier fields read after the closed schema has admitted the document.

use crate::capture::ChannelDeclaration;
use crate::files::FileRef;
use crate::manifest::{Completion, SourcePins};
use serde::Deserialize;

/// Public carrier declarations without source or runtime admission.
///
/// The committed schema closes every member and fixes the constant ones before
/// this view is decoded, so it holds only the members the analysis reads.
#[derive(Deserialize)]
pub(super) struct PublicManifest {
    /// Public carrier schema identifier.
    pub schema_id: String,
    /// Public cohort declaration, validated separately from source admission.
    pub native_source_cohort: String,
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
    /// Source-policy declaration, never a run-selected policy admission.
    pub source_contract_ref: FileRef,
}

impl PublicManifest {
    /// Move validated shared observations without changing public identity or root bytes.
    pub(crate) fn into_observations(self) -> crate::manifest::Manifest {
        crate::manifest::Manifest {
            profile: self.profile,
            evidence_class: self.evidence_class,
            run_id: self.run_id,
            epoch: self.epoch,
            step_count: self.step_count,
            fifo_capacity_records: self.fifo_capacity_records,
            capture_horizon_edges: self.capture_horizon_edges,
            source_files: self.source_files,
            sc_body_pins: self.sc_body_pins,
            tool_receipt: self.tool_receipt,
            input_trace: self.input_trace,
            numerical_trace: self.numerical_trace,
            numerical_projection: self.numerical_projection,
            reference_projection: self.reference_projection,
            service_trace: self.service_trace,
            channels: self.channels,
            completion: self.completion,
            clock_schedule_ref: self.clock_schedule_ref,
        }
    }
}
