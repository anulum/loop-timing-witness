// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Verify complete source-bound simulated neural acquisitions through an independent native API.

/// Firmware ELF admission and global symbol reading of AMP images.
pub mod amp_elf;
mod amp_elf_symbols;
/// Read errors and refusals of AMP inputs, as Python raises them.
pub mod amp_failure;
mod amp_files;
/// Firmware preprocessing dependency snapshots and record counts of AMP images.
pub mod amp_image_dependencies;
/// Runtime library snapshots of AMP images and captures.
pub mod amp_runtime_snapshot;
/// Rust dependency record reading of AMP images built with the Rust kernel.
pub mod amp_rust_dependencies;
mod amp_shell_words;
mod amp_snapshot_index;
mod binding;
/// The repeat campaign command, as Python's `analyze_campaign` runs it.
pub mod campaign_command;
mod capture;
mod checker_receipt;
mod clock_completion;
mod control_analysis;
/// Public CONTROL and COMPUTE run loading and event decoding.
pub mod control_api;
mod control_campaign;
mod control_campaign_outputs;
mod control_campaign_report;
mod control_command;
mod control_csv;
mod control_decimal;
mod control_domain;
mod control_events;
mod control_json;
mod control_json_text;
mod control_manifest;
mod control_number;
mod control_outputs;
mod control_paths;
mod control_pattern;
mod control_plots;
mod control_printable;
mod control_publication;
mod control_receipts;
mod control_report;
mod control_schema;
mod control_series;
mod control_text;
/// Corpus changes shared by the crate tests.
#[cfg(test)]
#[path = "../tests/support/corpus.rs"]
mod corpus;
/// Original device-tree decoding and the resource readers an AMP image binds.
pub mod device_tree;
mod device_tree_blob;
mod device_tree_interrupts;
mod device_tree_properties;
mod device_tree_resources;
mod device_tree_structure;
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
/// Corpus bytes and owned folders shared by the crate tests.
#[cfg(test)]
#[path = "../tests/support/unit_files.rs"]
mod unit_files;

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

/// Executors a consumer registration may bind.
pub use control_api::{
    ControlEvent, ControlInputs, IntervalRow, control_events_summary, control_run_report,
    decode_control_events, load_control_run, load_control_run_bytes,
};
/// Immutable report snapshot returned by the complete source-bound loader.
pub use public_api::{
    NeuralRunInputs, build_neural_run_report, load_neural_run, load_neural_run_with_registry,
};
pub use public_image::{ImageExecutor, NeuralExecutor};
/// Closed declaration reader, independent of full source admission.
pub use public_manifest::load_neural_manifest;
/// Atomic no-replacement publication of a complete report.
pub use public_publication::write_neural_report;
/// Consumer-owned reviewed registry types.
pub use public_registry::{NeuralEntry, NeuralKey, NeuralRegistry, neural_key};
