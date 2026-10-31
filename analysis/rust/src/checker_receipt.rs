// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Historical checker custody without source execution.

use crate::binding::BoundRun;
use crate::files::{digest, receipt};
use crate::traces::TraceFindings;
use serde::Deserialize;

/// Complete actual historical source-checker receipt, not a native source execution.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Checker {
    /// Original public-checker result.
    source_owned_public_checker_pass: bool,
    /// Original full requested rows.
    rows: u64,
    /// Original raw spike count.
    spikes: u64,
    /// Whole original stimulus digest.
    original_input_sha256: String,
    /// Original reference digest.
    reference_sha256: String,
    /// Actual projection digest.
    actual_projection_sha256: String,
    /// Original source model path, retained as historical metadata.
    model_module: String,
    /// Actual model body digest.
    model_sha256: String,
    /// Original constants path.
    constants_module: String,
    /// Actual constants body digest.
    constants_sha256: String,
}

/// Recompute historical receipt coherence without claiming fresh model execution.
pub(crate) fn checker(run: &BoundRun, traces: &TraceFindings) -> Result<Vec<String>, String> {
    let c: Checker = receipt(
        &run.files["source_owned_public_model_checker"],
        "historical source checker",
    )?;
    let _paths = (c.model_module, c.constants_module);
    if c.rows > 65535 || c.spikes > 65535 {
        return Err("Invalid complete actual receipt: historical source checker.".into());
    }
    let mut failures = Vec::new();
    for (name, actual, expected) in [
        ("rows", c.rows, u64::from(run.manifest.step_count)),
        ("spikes", c.spikes, traces.raw_spikes),
    ] {
        if actual != expected {
            failures.push(format!(
                "Historical source checker binding differs: {name}."
            ));
        }
    }
    for (name, actual, expected) in [
        (
            "original_input_sha256",
            c.original_input_sha256,
            digest(&run.files["original_stimulus"]),
        ),
        (
            "reference_sha256",
            c.reference_sha256,
            digest(&run.files["reference_projection"]),
        ),
        (
            "actual_projection_sha256",
            c.actual_projection_sha256,
            digest(&run.files["numerical_projection"]),
        ),
        (
            "model_sha256",
            c.model_sha256,
            run.manifest.sc_body_pins.model.clone(),
        ),
        (
            "constants_sha256",
            c.constants_sha256,
            run.manifest.sc_body_pins.constants.clone(),
        ),
    ] {
        if actual != expected {
            failures.push(format!(
                "Historical source checker binding differs: {name}."
            ));
        }
    }
    if !c.source_owned_public_checker_pass {
        failures.push(
            "Historical source checker binding differs: source_owned_public_checker_pass.".into(),
        );
    }
    Ok(failures)
}
