// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native public neural analysis command

//! Expose the complete Rust verifier with the same manifest/output-directory arguments.

use std::path::PathBuf;
use witness_analysis::{public_api, public_publication};

const USAGE: &str = "usage: loop-timing-witness-analyze-native MANIFEST --output-dir NEW_DIR";

/// Distinct usage and execution states retain their native CLI status meanings.
enum Arguments {
    Help,
    Analyze { manifest: PathBuf, output: PathBuf },
}

/// Parse caller-owned OS arguments without shell interpretation or lossy paths.
fn arguments() -> Result<Arguments, String> {
    let mut items = std::env::args_os().skip(1);
    let mut manifest = None;
    let mut output = None;
    let mut literal = false;
    while let Some(item) = items.next() {
        if !literal && (item == "-h" || item == "--help") {
            return Ok(Arguments::Help);
        }
        if !literal && item == "--" {
            literal = true;
            continue;
        }
        if !literal && item == "--output-dir" {
            if output.is_some() {
                return Err("output directory was provided more than once".into());
            }
            output = Some(PathBuf::from(
                items.next().ok_or("missing output directory")?,
            ));
        } else if !literal
            && item
                .to_str()
                .is_some_and(|value| value.starts_with("--output-dir="))
        {
            if output.is_some() {
                return Err("output directory was provided more than once".into());
            }
            let value = item
                .to_str()
                .and_then(|value| value.strip_prefix("--output-dir="))
                .ok_or("invalid output directory argument")?;
            output = Some(PathBuf::from(value));
        } else {
            if !literal && item.as_encoded_bytes().starts_with(b"-") {
                return Err("unsupported analysis argument".into());
            }
            if manifest.replace(PathBuf::from(item)).is_some() {
                return Err("expected one manifest".into());
            }
        }
    }
    Ok(Arguments::Analyze {
        manifest: manifest.ok_or("manifest is required")?,
        output: output.ok_or("output directory is required")?,
    })
}

/// Analyze and publish the entire admitted report before reporting a passing status.
fn run(manifest: PathBuf, output: PathBuf) -> Result<i32, String> {
    let inputs = public_api::load_neural_run(&manifest)?;
    let report = public_api::build_neural_run_report(&inputs);
    public_publication::write_neural_report(&output, &report)?;
    let passed = report["verification"]["whole"] == true;
    println!(
        "run analysis: {}: {}",
        if passed { "PASS" } else { "INVALID" },
        output.display()
    );
    Ok(if passed { 0 } else { 2 })
}

/// Emit one authored diagnostic and preserve native usage/analysis status boundaries.
fn main() {
    let parsed = arguments();
    let status = match parsed {
        Ok(Arguments::Help) => {
            println!("{USAGE}");
            0
        }
        Ok(Arguments::Analyze { manifest, output }) => match run(manifest, output) {
            Ok(status) => status,
            Err(reason) => {
                eprintln!("run analysis: FAIL: {reason}");
                1
            }
        },
        Err(reason) => {
            eprintln!("{USAGE}\nrun analysis: argument error: {reason}");
            2
        }
    };
    std::process::exit(status);
}
