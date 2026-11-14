// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — command dispatch and control-run analysis

//! Choose the neural or control analysis for one manifest and run the
//! control analysis end to end, as Python's `analyze_run.main` does.
//!
//! The manifest is read once, without following a symbolic link, from its
//! resolved directory and up to 16 MiB, as `read_run_dispatch_bytes` reads it,
//! and decoded as Python's `parse_dispatch_json_object` decodes it: strict
//! JSON nested at most 64 deep, with integers and unpaired surrogates left to
//! the chosen analysis. A manifest with a `schema_id` member is a neural run;
//! any other is loaded from the same bytes as a CONTROL or COMPUTE run,
//! analysed and published.

use crate::control_json::decode_dispatch_object;
use crate::control_manifest::load;
use crate::control_outputs::report_files;
use crate::control_publication::publish_report_directory;
use crate::control_report::build_report;
use rustix::fs::{Mode, OFlags, fstat, openat};
use std::io::Read;
use std::path::Path;

/// Largest manifest the dispatcher reads, in bytes.
const DISPATCH_LIMIT: u64 = 16 * 1024 * 1024;
/// The dispatcher's refusal prefix.
const REQUIRED: &str = "A finite regular strict JSON manifest is required.";

/// Which analysis a manifest selects.
pub(crate) enum Dispatch {
    /// A neural step run, analysed from its own path.
    Neural,
    /// A CONTROL or COMPUTE run, with the root bytes already read.
    Control(Vec<u8>),
}

/// Read the root bytes as Python's `read_run_dispatch_bytes`; `None` is any failure.
///
/// Python resolves the parent strictly and opens the result; every failure
/// gives the same refusal, so opening the parent itself through the kernel's
/// own path walk accepts and refuses exactly the same parents.
fn root_bytes(path: &Path) -> Option<Vec<u8>> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let flags = OFlags::RDONLY | OFlags::CLOEXEC;
    let directory = openat(
        rustix::fs::CWD,
        parent,
        flags | OFlags::DIRECTORY,
        Mode::empty(),
    )
    .ok()?;
    let file = openat(
        &directory,
        path.file_name()?,
        flags | OFlags::NOFOLLOW | OFlags::NONBLOCK,
        Mode::empty(),
    )
    .ok()?;
    let regular = fstat(&file)
        .is_ok_and(|status| rustix::fs::FileType::from_raw_mode(status.st_mode).is_file());
    if !regular {
        return None;
    }
    let mut raw = Vec::new();
    std::fs::File::from(file)
        .take(DISPATCH_LIMIT + 1)
        .read_to_end(&mut raw)
        .ok()?;
    (u64::try_from(raw.len()).expect("bounded read") <= DISPATCH_LIMIT).then_some(raw)
}

/// Select the analysis of a manifest, as Python's `dispatch_analysis`.
pub(crate) fn dispatch(path: &Path) -> Result<Dispatch, String> {
    let raw = root_bytes(path).ok_or_else(|| {
        format!("{REQUIRED} Cannot acquire a finite regular run manifest for analysis.")
    })?;
    let manifest = decode_dispatch_object(&raw, "analysis manifest")
        .map_err(|refusal| format!("{REQUIRED} {refusal}"))?;
    Ok(if manifest.contains_key("schema_id") {
        Dispatch::Neural
    } else {
        Dispatch::Control(raw)
    })
}

/// Load, analyse and publish one CONTROL or COMPUTE run, as Python's command does.
pub(crate) fn analyze_control(manifest: &Path, output: &Path, raw: &[u8]) -> Result<(), String> {
    let run = load(manifest, Some(raw))?;
    let (report, rows) = build_report(&run.manifest, &run.domain, &run.files, &run.directory)?;
    publish_report_directory(output, &report_files(&report, &rows))
}
