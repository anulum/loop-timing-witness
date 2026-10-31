// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Verify complete source-bound simulated neural acquisitions through an independent native API.

mod binding;
mod capture;
mod checker_receipt;
mod clock_completion;
/// Whole original file reference and finite complete-byte acquisition.
pub mod files;
mod json_integer;
mod manifest;
mod native_clock;
mod native_jobs;
mod native_policy;
mod native_runtime;
mod receipts;
mod reset;
mod rows;
mod traces;

/// Closed public neural carrier declarations, separate from complete run verification.
pub mod public_manifest;
mod public_manifest_fields;

/// Full public acquisition loader and immutable whole-verification report snapshots.
pub mod public_api;
mod public_binding;
mod public_capture;
mod public_checker;
mod public_checker_fields;
mod public_checker_receipts;
/// The analysis command, run against a caller-selected registry.
pub mod public_command;
mod public_execution;
mod public_image;
mod public_policy;
/// Atomic whole-report file publication without replacing existing data.
pub mod public_publication;
/// Consumer-owned reviewed registrations selected by admission identity.
pub mod public_registry;
mod public_report;
/// Complete source-checker installation binding, separate from source admission.
pub mod public_runtime;
mod public_temporary;
mod public_tools;
mod public_trace;
mod selected_profile;
mod strict_json;

/// Immutable report snapshot returned by the complete source-bound loader.
pub use public_api::{
    NeuralRunInputs, build_neural_run_report, load_neural_run, load_neural_run_with_registry,
};
/// Executors a consumer registration may bind.
pub use public_image::{ImageExecutor, NeuralExecutor};
/// Closed declaration reader, independent of full source admission.
pub use public_manifest::load_neural_manifest;
/// Atomic no-replacement publication of a complete report.
pub use public_publication::write_neural_report;
/// Consumer-owned reviewed registry types.
pub use public_registry::{NeuralEntry, NeuralKey, NeuralRegistry, neural_key};
