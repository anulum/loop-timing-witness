// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native analysis command over a selected registry

//! Run the analysis command against the registry its caller selects.
//!
//! The installed command passes the packaged reviewed registry. A consumer that
//! reviews its own entries can run the same command, with the same arguments,
//! messages and statuses, against its own registry.

use crate::public_api::{build_neural_run_report, load_neural_run_with_registry};
use crate::public_publication::write_neural_report;
use crate::public_registry::NeuralRegistry;
use std::ffi::OsString;
use std::io::Write;
use std::path::{Path, PathBuf};

/// Usage line of the analysis command.
pub const USAGE: &str = "usage: loop-timing-witness-analyze-native MANIFEST --output-dir NEW_DIR";

/// Distinct usage and execution requests keep their command status meanings.
enum Arguments {
    Help,
    Analyze { manifest: PathBuf, output: PathBuf },
}

/// One option recognised before the literal separator.
enum Item {
    Help,
    Literal,
    Output(Option<OsString>),
    Operand,
}

/// Classify one argument without shell interpretation or lossy conversion.
fn classify(item: &OsString) -> Item {
    match item.to_str() {
        Some("-h" | "--help") => Item::Help,
        Some("--") => Item::Literal,
        Some("--output-dir") => Item::Output(None),
        Some(text) => text
            .strip_prefix("--output-dir=")
            .map_or(Item::Operand, |value| Item::Output(Some(value.into()))),
        None => Item::Operand,
    }
}

/// Parse caller-owned OS arguments into one request.
fn parse(arguments: &[OsString]) -> Result<Arguments, String> {
    let mut items = arguments.iter();
    let mut manifest = None;
    let mut output = None;
    let mut literal = false;
    while let Some(item) = items.next() {
        let kind = if literal {
            Item::Operand
        } else {
            classify(item)
        };
        match kind {
            Item::Help => return Ok(Arguments::Help),
            Item::Literal => literal = true,
            Item::Output(inline) => {
                if output.is_some() {
                    return Err("output directory was provided more than once".into());
                }
                let value = match inline {
                    Some(value) => value,
                    None => items.next().ok_or("missing output directory")?.clone(),
                };
                output = Some(PathBuf::from(value));
            }
            Item::Operand => {
                if !literal && item.as_encoded_bytes().starts_with(b"-") {
                    return Err("unsupported analysis argument".into());
                }
                if manifest.replace(PathBuf::from(item)).is_some() {
                    return Err("expected one manifest".into());
                }
            }
        }
    }
    Ok(Arguments::Analyze {
        manifest: manifest.ok_or("manifest is required")?,
        output: output.ok_or("output directory is required")?,
    })
}

/// Analyze and publish the entire admitted report; return whether it passed.
fn analyze(manifest: &Path, output: &Path, registry: &NeuralRegistry) -> Result<bool, String> {
    let inputs = load_neural_run_with_registry(manifest, registry)?;
    let report = build_neural_run_report(&inputs);
    write_neural_report(output, &report)?;
    Ok(report["verification"]["whole"] == true)
}

/// Run the analysis command and return its status.
///
/// Status 0 publishes a passing report and status 2 a failing one; 1 is a
/// refusal with nothing published, and 2 also reports an argument error.
/// The report is published before a passing or failing line is written.
pub fn run(
    arguments: &[OsString],
    registry: &NeuralRegistry,
    stdout: &mut dyn Write,
    stderr: &mut dyn Write,
) -> i32 {
    match parse(arguments) {
        Ok(Arguments::Help) => {
            let _ = writeln!(stdout, "{USAGE}");
            0
        }
        Ok(Arguments::Analyze { manifest, output }) => {
            match analyze(&manifest, &output, registry) {
                Ok(passed) => {
                    let verdict = if passed { "PASS" } else { "INVALID" };
                    let _ = writeln!(stdout, "run analysis: {verdict}: {}", output.display());
                    if passed { 0 } else { 2 }
                }
                Err(reason) => {
                    let _ = writeln!(stderr, "run analysis: FAIL: {reason}");
                    1
                }
            }
        }
        Err(reason) => {
            let _ = writeln!(stderr, "{USAGE}\nrun analysis: argument error: {reason}");
            2
        }
    }
}
