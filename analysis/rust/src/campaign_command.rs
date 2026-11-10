// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native repeat campaign command

//! Analyse every repeat of one run configuration and publish the campaign
//! report, with the statuses, lines and files of Python's
//! `loop-timing-witness-campaign` command.
//!
//! The campaign is loaded, each repeat analysed and the pooled and spread
//! statistics built as the Python analysis builds them; the report directory
//! is published atomically, as a run report is. A published complete campaign
//! exits 0 and an incomplete one 2, after its nonconformities; a refused
//! campaign or an unwritable report exits 1 with nothing published.

use crate::control_campaign::load_campaign;
use crate::control_campaign_outputs::campaign_files;
use crate::control_campaign_report::build_campaign_report;
use crate::control_paths::pure_path;
use crate::control_publication::publish_report_directory;
use crate::public_command::{Arguments, parse};
use serde_json::Value;
use std::ffi::OsString;
use std::io::Write;
use std::path::Path;

/// Usage line of the campaign command.
pub const USAGE: &str = "usage: loop-timing-witness-campaign-native CAMPAIGN --output-dir NEW_DIR";

/// Load, analyse and publish one campaign; return its report.
fn analyze(campaign: &Path, output: &Path) -> Result<Value, String> {
    let report = build_campaign_report(&load_campaign(campaign)?)?;
    publish_report_directory(output, &campaign_files(&report))?;
    Ok(report)
}

/// Run the campaign command and return its status.
///
/// Status 0 publishes a complete campaign and 2 an incomplete one, whose
/// nonconformities follow its line; 1 is a refusal with nothing published,
/// and 2 also reports an argument error. The report is published before its
/// line is written.
pub fn run(arguments: &[OsString], stdout: &mut dyn Write, stderr: &mut dyn Write) -> i32 {
    match parse(arguments) {
        Ok(Arguments::Help) => {
            let _ = writeln!(stdout, "{USAGE}");
            0
        }
        Ok(Arguments::Analyze { manifest, output }) => match analyze(&manifest, &output) {
            Ok(report) => {
                let shown = pure_path(&output);
                if report["status"] == "complete" {
                    let _ = writeln!(stdout, "repeat campaign: COMPLETE: {shown}");
                    return 0;
                }
                let _ = writeln!(stdout, "repeat campaign: INCOMPLETE: {shown}");
                for item in report["plan"]["nonconformities"]
                    .as_array()
                    .expect("nonconformity list")
                {
                    let _ = writeln!(stdout, "  {}", item.as_str().expect("nonconformity"));
                }
                2
            }
            Err(reason) => {
                let _ = writeln!(stderr, "repeat campaign: FAIL: {reason}");
                1
            }
        },
        Err(reason) => {
            let _ = writeln!(stderr, "{USAGE}\nrepeat campaign: argument error: {reason}");
            2
        }
    }
}
