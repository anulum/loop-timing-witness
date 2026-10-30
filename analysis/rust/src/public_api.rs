// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete public neural analysis API

//! Analyze complete admitted acquisitions, keeping source selection consumer-owned.

use crate::public_registry::NeuralRegistry;
use serde_json::Value;
use std::path::Path;

/// Immutable report snapshot created by the complete public neural loader.
///
/// Private fields prevent callers from substituting declarations or partial capture
/// envelopes for full source, runtime, numerical and completion verification.
pub struct NeuralRunInputs {
    report: Value,
}

/// Load the entire admitted acquisition and execute its actual source-owned checker.
///
/// # Errors
///
/// Refuses unsupported source admission, malformed or unbound original inputs,
/// unavailable selected runtime boundaries, and unexpected analysis failures.
pub fn load_neural_run(path: &Path) -> Result<NeuralRunInputs, String> {
    load_neural_run_with_registry(path, &NeuralRegistry::reviewed())
}

/// Load the entire acquisition against the consumer's own reviewed registry.
///
/// The registry is the consumer's review; acquisition data never selects it or
/// an entry. [`NeuralRegistry::reviewed`] holds the packaged entries.
///
/// # Errors
///
/// Refuses as [`load_neural_run`] does, and when the selected entry's source
/// policy differs from its registered identity.
pub fn load_neural_run_with_registry(
    path: &Path,
    registry: &NeuralRegistry,
) -> Result<NeuralRunInputs, String> {
    let bound = crate::public_binding::load(path, registry)?;
    let report = crate::public_report::analyze(bound)?;
    Ok(NeuralRunInputs { report })
}

/// Return a fresh whole report without repeating source-checker jobs or file reads.
pub fn build_neural_run_report(inputs: &NeuralRunInputs) -> Value {
    inputs.report.clone()
}
